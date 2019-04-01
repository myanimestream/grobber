import logging
from typing import Optional, Set, cast

from bs4 import Tag

from grobber.anime.sources.vidstreaming import BASE_URL, VidstreamingAnime, parse_raw_title
from grobber.languages import Language
from grobber.request import Request
from grobber.uid import MediumType
from .. import IndexScraper, IndexScraperCategory, MaxPageIndexIndexScraper, Medium, UpdateUntilLastStateIndexScraper, create_medium, \
    get_next_page_index_selector_impl, index_scraper

log = logging.getLogger(__name__)

NEW_SUB_LIST_URL = BASE_URL
NEW_DUB_LIST_URL = BASE_URL + "/recently-added-dub"

ONGOING_LIST_URL = BASE_URL + "/ongoing-series"


class _BaseVidstreamingIndexScraper(IndexScraper):
    LIST_URL: str

    async def create_request(self, page_index: int) -> Request:
        return Request(self.LIST_URL, {"page": page_index + 1})

    async def extract_media(self, req: Request) -> Set[Medium]:
        bs = await req.bs
        items = bs.select(".listing.items .video-block a")

        media: Set[Medium] = set()

        for item in items:
            item = cast(Tag, item)

            try:
                href = item["href"]
            except Exception:
                log.exception(f"{self!r} couldn't extract href from item: {item!r}")
                continue
            else:
                href = BASE_URL + href

            raw_title_container: Optional[Tag] = item.select_one(".name")
            if not raw_title_container:
                log.error(f"{self!r} couldn't find raw title container for item: {item!r}")
                continue

            raw_title = raw_title_container.text
            title, dubbed, episode_index = parse_raw_title(raw_title)

            thumbnail_container: Optional[Tag] = item.select_one(".img .picture img")
            if thumbnail_container:
                thumbnail = thumbnail_container.get("src", None)
            else:
                thumbnail = None

            medium = create_medium(self.source_cls, MediumType.ANIME, title, href,
                                   language=Language.ENGLISH,
                                   dubbed=dubbed,
                                   episode_count=episode_index + 1,
                                   thumbnail=thumbnail)
            media.add(medium)

        return media

    async def get_next_page_index(self, req: Request, current_page_index: int) -> Optional[int]:
        return await get_next_page_index_selector_impl(self, req, current_page_index, ".pagination .next")


@index_scraper(VidstreamingAnime, IndexScraperCategory.ONGOING)
class VidstreamingOngoingIndexScraper(_BaseVidstreamingIndexScraper):
    LIST_URL = ONGOING_LIST_URL


class _BaseVidstreamingUpdateIndexScraper(UpdateUntilLastStateIndexScraper, MaxPageIndexIndexScraper, _BaseVidstreamingIndexScraper):
    ...


@index_scraper(VidstreamingAnime, IndexScraperCategory.NEW)
class VidstreamingNewSubIndexScraper(_BaseVidstreamingUpdateIndexScraper):
    LIST_URL = NEW_SUB_LIST_URL


@index_scraper(VidstreamingAnime, IndexScraperCategory.NEW)
class VidstreamingNewDubIndexScraper(_BaseVidstreamingUpdateIndexScraper):
    LIST_URL = NEW_DUB_LIST_URL
