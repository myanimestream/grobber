import abc
import asyncio
import logging
from collections import deque
from contextlib import suppress
from enum import Enum
from typing import Any, Callable, Collection, Deque, Dict, Iterable, List, Optional, Set, Tuple, Type, TypeVar

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import UpdateOne
from pymongo.results import BulkWriteResult

from grobber.anime import SourceAnime
from grobber.request import Request
from .medium import Medium, medium_to_document

__all__ = ["SCRAPE_DELAY",
           "IndexScraper", "get_next_page_index_selector_impl",
           "UpdateUntilLastStateIndexScraper",
           "MaxPageIndexIndexScraper",
           "IndexScraperCategory", "index_scraper",
           "is_index_scraper",
           "get_index_scraper_id", "get_index_scraper_source", "get_index_scraper_category"]

log = logging.getLogger(__name__)

SCRAPE_DELAY: float = 2


class IndexScraper(abc.ABC):
    collection: AsyncIOMotorCollection
    meta_collection: AsyncIOMotorCollection

    def __init__(self, collection: AsyncIOMotorCollection, meta_collection: AsyncIOMotorCollection) -> None:
        self.collection = collection
        self.meta_collection = meta_collection

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        return f"{cls_name}"

    @property
    def source_id(self) -> str:
        source_id = get_index_scraper_id(self)
        if not source_id:
            raise ValueError(f"{self} source id not set (using the \"index_scraper\" decorator)")
        return source_id

    @property
    def source_cls(self) -> str:
        source = get_index_scraper_source(self)
        if not source:
            raise ValueError(f"{self} source not set (using the \"index_scraper\" decorator)")
        return source.get_qualcls()

    @abc.abstractmethod
    async def create_request(self, page_index: int) -> Optional[Request]:
        ...

    @abc.abstractmethod
    async def extract_media(self, req: Request) -> Collection[Medium]:
        ...

    async def safe_extract_media(self, req: Request) -> Optional[Collection[Medium]]:
        try:
            return await self.extract_media(req)
        except Exception:
            log.exception(f"{self!r} failed to extract media from {req} (ignored)")
            return None

    @abc.abstractmethod
    async def get_next_page_index(self, req: Request, current_page_index: int) -> Optional[int]:
        ...

    async def upload_media(self, media: Iterable[Medium]) -> None:
        requests: List[UpdateOne] = []
        for medium in media:
            doc = medium_to_document(medium)
            with suppress(KeyError):
                del doc["_id"]

            update = {"$set": doc}
            request = UpdateOne({"_id": medium.raw_uid}, update, upsert=True)
            requests.append(request)

        if requests:
            log.debug(f"{self!r} performing {len(requests)} database requests")
            result: BulkWriteResult = await self.collection.bulk_write(requests, ordered=False)
            log.debug(f"{self!r} modified: {result.modified_count}, created: {result.upserted_count}")
        else:
            log.debug(f"{self!r} no database requests to perform")

    @classmethod
    async def wait_scrape_delay(cls) -> None:
        await asyncio.sleep(SCRAPE_DELAY)

    async def scrape_once(self, page_index: int) -> Tuple[Optional[Request], Optional[Collection[Medium]], Optional[int]]:
        log.info(f"{self!r} scraping page index {page_index}")

        log.debug(f"{self!r} creating request for page index {page_index}")
        req = await self.create_request(page_index)
        if req is None:
            log.info(f"{self!r} no request created, breaking out")
            return None, None, None

        page_media = await self.safe_extract_media(req)
        next_page_index = await self.get_next_page_index(req, page_index)

        return req, page_media, next_page_index

    # noinspection PyMethodMayBeStatic
    async def should_continue(self, req: Request, page_media: Optional[Collection[Medium]], current_page_index: int, next_page_index: int) -> bool:
        return True

    async def scrape(self) -> None:
        page_index: Optional[int] = 0

        while True:
            req, page_media, next_page_index = await self.scrape_once(page_index)
            if page_media is None:
                log.info(f"{self!r} couldn't extract any media for page index {page_index} from {req!r}")
            else:
                log.debug(f"{self!r} extracted {len(page_media)} media")
                await self.upload_media(page_media)

            if next_page_index is None:
                break

            if not await self.should_continue(req, page_media, page_index, next_page_index):
                break

            page_index = next_page_index
            await self.wait_scrape_delay()

        log.info(f"{self!r} done scraping")


async def get_next_page_index_selector_impl(index_scraper: IndexScraper, req: Request, current_page_index: int, selector: str) -> Optional[int]:
    bs = await req.bs

    next_button = bs.select_one(selector)
    if not next_button:
        log.info(f"{index_scraper!r} couldn't find next button, assuming {current_page_index} is the last page index! {req!r}")
        return None

    return current_page_index + 1


class UpdateUntilLastStateIndexScraper(IndexScraper, abc.ABC):
    _recent_medium_titles: Deque[str]
    _first_page_titles: Optional[Set[str]]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._recent_medium_titles = deque(maxlen=200)

    async def upload_first_page_titles(self, titles: Iterable[str]) -> None:
        titles = list(titles)
        log.info(f"{self!r} uploading first page titles: {titles}")
        await self.meta_collection.update_one({"_id": self.source_id}, {"$set": {"first_page_titles": titles}}, upsert=True)

    async def _get_first_page_titles(self) -> Optional[Set[str]]:
        doc: Optional[Dict[str, Any]] = await self.meta_collection.find_one(self.source_id, projection=["first_page_titles"])
        if not doc:
            return None

        titles: Optional[List[str]] = doc.get("first_page_titles")
        if titles is None:
            return None
        else:
            return set(titles)

    async def get_first_page_titles(self) -> Optional[Set[str]]:
        try:
            titles: Optional[Set[str]] = self._first_page_titles
        except AttributeError:
            titles = self._first_page_titles = await self._get_first_page_titles()

        return titles

    async def check_first_page_titles_different(self) -> bool:
        old_page_titles = await self.get_first_page_titles()
        if old_page_titles is None:
            return True

        recent_titles = set(self._recent_medium_titles)
        return not old_page_titles.issubset(recent_titles)

    def add_recent_media_titles(self, titles: Iterable[str]) -> None:
        self._recent_medium_titles.extend(titles)

    async def should_continue(self, req: Request, page_media: Optional[Collection[Medium]], current_page_index: int, next_page_index: int) -> bool:
        should_continue = await super().should_continue(req, page_media, current_page_index, next_page_index)

        if not should_continue or page_media is None:
            return should_continue

        titles: Set[str] = {medium.title for medium in page_media}

        self.add_recent_media_titles(titles)
        hashes_different = await self.check_first_page_titles_different()

        if current_page_index == 0:
            await self.upload_first_page_titles(titles)

        if hashes_different:
            return True
        else:
            log.info(f"{self!r} reached page index {current_page_index} whose media is equal to previous hash.")
            return False


class MaxPageIndexIndexScraper(IndexScraper, abc.ABC):
    MAX_PAGE_INDEX: int = 80

    async def should_continue(self, req: Request, page_media: Optional[Collection[Medium]], current_page_index: int, next_page_index: int) -> bool:
        if current_page_index >= self.MAX_PAGE_INDEX:
            log.info(f"{self!r} not returning next page index because page index reached limit {self.MAX_PAGE_INDEX}")
            return False

        return await super().should_continue(req, page_media, current_page_index, next_page_index)


class IndexScraperCategory(Enum):
    FULL = "full"
    NEW = "new"
    ONGOING = "ongoing"


T = TypeVar("T")

INDEX_SCRAPER_ID_ATTR = "__scraper_id__"
INDEX_SCRAPER_SOURCE_ATTR = "__scraper_source__"
INDEX_SCRAPER_CATEGORY_ATTR = "__scraper_category__"


def index_scraper(source: SourceAnime, category: IndexScraperCategory, *, index_scraper_id: str = None) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        setattr(cls, INDEX_SCRAPER_ID_ATTR, index_scraper_id or cls.__qualname__)
        setattr(cls, INDEX_SCRAPER_SOURCE_ATTR, source)
        setattr(cls, INDEX_SCRAPER_CATEGORY_ATTR, category)
        return cls

    return decorator


def is_index_scraper(obj: Any) -> bool:
    try:
        getattr(obj, INDEX_SCRAPER_ID_ATTR)
        getattr(obj, INDEX_SCRAPER_SOURCE_ATTR)
        getattr(obj, INDEX_SCRAPER_CATEGORY_ATTR)
    except AttributeError:
        return False
    else:
        return True


def get_index_scraper_id(index_scraper: Any) -> Optional[str]:
    return getattr(index_scraper, INDEX_SCRAPER_ID_ATTR, None)


def get_index_scraper_source(index_scraper: Any) -> Optional[Type[SourceAnime]]:
    return getattr(index_scraper, INDEX_SCRAPER_SOURCE_ATTR, None)


def get_index_scraper_category(index_scraper: Any) -> Optional[INDEX_SCRAPER_CATEGORY_ATTR]:
    return getattr(index_scraper, INDEX_SCRAPER_CATEGORY_ATTR, None)
