import logging
from abc import ABC
from typing import List, Optional, Set

import bs4

from grobber.anime.sources.animevibe import AnimeVibeAnime, animevibe_pool, extract_stack_info
from grobber.languages import Language
from grobber.request import Request
from grobber.uid import MediumType
from .. import IndexScraper, IndexScraperCategory, Medium, create_medium, \
    get_next_page_index_selector_impl, index_scraper

log = logging.getLogger(__name__)


class AnimeVibeFullBase(IndexScraper, ABC):
    async def extract_media(self, req: Request) -> Set[Medium]:
        bs = await req.bs
        items: List[bs4.Tag] = bs.select(".td-ss-main-content .td-animation-stack")

        media: Set[Medium] = set()

        for item in items:
            info = extract_stack_info(item)

            medium = create_medium(self.source_cls, MediumType.ANIME, info.title, info.url,
                                   language=Language.ENGLISH,
                                   dubbed=info.dubbed,
                                   thumbnail=info.thumbnail)
            media.add(medium)

        return media

    async def get_next_page_index(self, req: Request, current_page_index: int) -> Optional[int]:
        return await get_next_page_index_selector_impl(self, req, current_page_index, ".page-nav .td-icon-menu-right")


@index_scraper(AnimeVibeAnime, IndexScraperCategory.FULL)
class AnimeVibeSubFull(AnimeVibeFullBase):
    async def create_request(self, page_index: int) -> Request:
        return Request(f"{{{animevibe_pool}}}/a/category/sub/page/{page_index + 1}/")


@index_scraper(AnimeVibeAnime, IndexScraperCategory.FULL)
class AnimeVibeDubFull(AnimeVibeFullBase):
    async def create_request(self, page_index: int) -> Request:
        return Request(f"{{{animevibe_pool}}}/a/category/dub/page/{page_index + 1}/")
