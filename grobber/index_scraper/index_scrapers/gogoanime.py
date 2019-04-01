import logging
from typing import Optional, Set, cast

from bs4 import Tag

from grobber.anime.sources.gogoanime import BASE_URL, GogoAnime, parse_raw_title
from grobber.languages import Language
from grobber.request import Request
from grobber.uid import MediumType
from .. import IndexScraper, IndexScraperCategory, MaxPageIndexIndexScraper, Medium, UpdateUntilLastStateIndexScraper, create_medium, \
    get_next_page_index_selector_impl, index_scraper

log = logging.getLogger(__name__)

FULL_LIST_URL = BASE_URL + "/anime-list.html"
NEW_LIST_URL = BASE_URL + "//page-recent-release.html"


@index_scraper(GogoAnime, IndexScraperCategory.FULL)
class GogoAnimeFullIndexScraper(IndexScraper):
    async def create_request(self, page_index: int) -> Request:
        return Request(FULL_LIST_URL, {"page": page_index + 1})

    async def extract_media(self, req: Request) -> Set[Medium]:
        bs = await req.bs
        listings = bs.select(".anime_list_body .listing a")

        media: Set[Medium] = set()

        for listing in listings:
            listing = cast(Tag, listing)

            try:
                href: str = BASE_URL + listing["href"]
                raw_title: str = listing.text
            except Exception:
                log.exception(f"{self!r} couldn't extract title/href from listing: {listing!r}")
                continue

            title, dubbed = parse_raw_title(raw_title)
            medium = create_medium(self.source_cls, MediumType.ANIME, title, href,
                                   language=Language.ENGLISH, dubbed=dubbed)
            media.add(medium)

        return media

    async def get_next_page_index(self, req: Request, current_page_index: int) -> Optional[int]:
        return await get_next_page_index_selector_impl(self, req, current_page_index, ".pagination-list .selected:not(:last-child)")


@index_scraper(GogoAnime, IndexScraperCategory.NEW)
class GogoAnimeNewSubIndexScraper(UpdateUntilLastStateIndexScraper, MaxPageIndexIndexScraper):
    async def create_request(self, page_index: int) -> Request:
        return Request(NEW_LIST_URL, {"page": page_index + 1, "type": 1})

    async def extract_media(self, req: Request) -> Set[Medium]:
        bs = await req.bs
        items = bs.select(".last_episodes .items li")

        media: Set[Medium] = set()

        for item in items:
            item = cast(Tag, item)

            name_container: Optional[Tag] = item.select_one(".name a")

            try:
                href: str = BASE_URL + name_container["href"]
                raw_title: str = name_container.text
            except Exception:
                log.exception(f"{self!r} couldn't extract title/href from item: {item!r}")
                continue

            title, dubbed = parse_raw_title(raw_title)

            thumbnail_container: Optional[Tag] = item.select_one(".img img")
            if thumbnail_container:
                thumbnail = thumbnail_container.get("src", None)
            else:
                thumbnail = None

            episode_container: Optional[Tag] = item.select_one(".episode")
            if episode_container:
                raw_episode: str = episode_container.text
                raw_episode_count = raw_episode.rsplit(maxsplit=1)[-1]

                try:
                    # handle decimal numbers, round down to get effective number
                    episode_count = int(float(raw_episode_count))
                except ValueError:
                    log.info(f"{self!r} Couldn't parse episode count \"{raw_episode_count!r}\" from \"{raw_episode}\" for item: {item}")
                    episode_count = None
            else:
                log.debug(f"{self!r} Couldn't find episode container for item: {item}")
                episode_count = None

            medium = create_medium(self.source_cls, MediumType.ANIME, title, href,
                                   language=Language.ENGLISH,
                                   dubbed=dubbed,
                                   thumbnail=thumbnail,
                                   episode_count=episode_count)
            media.add(medium)

        return media

    async def get_next_page_index(self, req: Request, current_page_index: int) -> Optional[int]:
        return await get_next_page_index_selector_impl(self, req, current_page_index, ".pagination-list .selected:not(:last-child)")


@index_scraper(GogoAnime, IndexScraperCategory.NEW)
class GogoAnimeNewDubIndexScraper(GogoAnimeNewSubIndexScraper):
    async def create_request(self, page_index: int) -> Request:
        return Request(NEW_LIST_URL, {"page": page_index + 1, "type": 2})
