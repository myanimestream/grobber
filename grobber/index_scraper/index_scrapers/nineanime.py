import logging
from typing import List, Optional, Set, cast

from bs4 import Tag
from yarl import URL

from grobber.anime.sources.nineanime import BASE_URL, NineAnime, extract_episode_count, parse_raw_title
from grobber.languages import Language
from grobber.request import Request
from grobber.uid import MediumType
from .. import IndexScraper, IndexScraperCategory, MaxPageIndexIndexScraper, Medium, UpdateUntilLastStateIndexScraper, create_medium, \
    get_next_page_index_selector_impl, index_scraper

log = logging.getLogger(__name__)

NEW_LIST_URL = BASE_URL + "/updated"
FULL_LIST_URL = BASE_URL + "/az-list"


@index_scraper(NineAnime, IndexScraperCategory.FULL)
class NineAnimeFullIndexScraper(IndexScraper):
    async def create_request(self, page_index: int) -> Request:
        return Request(FULL_LIST_URL, {"page": page_index + 1})

    async def extract_media(self, req: Request) -> Set[Medium]:
        bs = await req.bs
        items = bs.select(".items .item")

        media: Set[Medium] = set()

        for item in items:
            item = cast(Tag, item)

            raw_title_container: Optional[Tag] = item.select_one(".info .name")
            if not raw_title_container:
                log.error(f"{self!r} couldn't find raw title container for item: {item!r}")
                continue

            try:
                href = URL(raw_title_container["href"])
            except Exception:
                log.exception(f"{self!r} couldn't extract href from item: {item!r}")
                continue
            else:
                href = BASE_URL + href.path_qs

            raw_title = raw_title_container.text
            title, dubbed = parse_raw_title(raw_title)

            aliases: List[str] = []
            try:
                japanese_raw_title = raw_title_container["data-jtitle"]
            except KeyError:
                pass
            else:
                if japanese_raw_title and japanese_raw_title != raw_title:
                    japanese_title = parse_raw_title(japanese_raw_title)[0]
                    aliases.append(japanese_title)

            thumbnail_container: Optional[Tag] = item.select_one(".thumb img")
            if thumbnail_container:
                thumbnail = thumbnail_container.get("src", None)
            else:
                thumbnail = None

            medium = create_medium(self.source_cls, MediumType.ANIME, title, href,
                                   language=Language.ENGLISH,
                                   dubbed=dubbed,
                                   thumbnail=thumbnail,
                                   aliases=aliases)
            media.add(medium)

        return media

    async def get_next_page_index(self, req: Request, current_page_index: int) -> Optional[int]:
        return await get_next_page_index_selector_impl(self, req, current_page_index, ".paging-wrapper .pull-right:not(.disabled)")


@index_scraper(NineAnime, IndexScraperCategory.NEW)
class NineAnimeNewIndexScraper(UpdateUntilLastStateIndexScraper, MaxPageIndexIndexScraper):
    async def create_request(self, page_index: int) -> Request:
        return Request(NEW_LIST_URL, {"page": page_index + 1})

    async def extract_media(self, req: Request) -> Set[Medium]:
        bs = await req.bs
        items = bs.select(".film-list .item .inner")

        media: Set[Medium] = set()

        for item in items:
            item = cast(Tag, item)

            raw_title_container: Optional[Tag] = item.select_one(".name")
            if not raw_title_container:
                log.error(f"{self!r} couldn't find raw title container for item: {item!r}")
                continue

            try:
                href = URL(raw_title_container["href"])
            except Exception:
                log.exception(f"{self!r} couldn't extract href from item: {item!r}")
                continue
            else:
                href = BASE_URL + href.path_qs

            raw_title = raw_title_container.text
            title, dubbed = parse_raw_title(raw_title)

            aliases: List[str] = []
            try:
                japanese_raw_title = raw_title_container["data-jtitle"]
            except KeyError:
                pass
            else:
                if japanese_raw_title and japanese_raw_title != raw_title:
                    # use the japanese title and use the "real title" as an alias
                    aliases.append(title)
                    title = parse_raw_title(japanese_raw_title)[0]

            thumbnail_container: Optional[Tag] = item.select_one(".poster img")
            if thumbnail_container:
                thumbnail = thumbnail_container.get("src", None)
            else:
                thumbnail = None

            episode_container: Optional[Tag] = item.select_one(".status .ep")
            episode_count = extract_episode_count(episode_container)

            medium = create_medium(self.source_cls, MediumType.ANIME, title, href,
                                   language=Language.ENGLISH,
                                   dubbed=dubbed,
                                   thumbnail=thumbnail,
                                   episode_count=episode_count,
                                   aliases=aliases)
            media.add(medium)

        return media

    async def get_next_page_index(self, req: Request, current_page_index: int) -> Optional[int]:
        return await get_next_page_index_selector_impl(self, req, current_page_index, ".paging-wrapper .pull-right:not(.disabled)")
