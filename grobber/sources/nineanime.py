import re
from typing import Iterator, List

from pyppeteer.page import Page

from . import register_source
from ..decorators import cached_property
from ..languages import Language
from ..models import Anime, Episode, SearchResult, Stream, get_certainty
from ..request import DefaultUrlFormatter, Request
from ..streams import get_stream
from ..url_pool import UrlPool
from ..utils import anext

BASE_URL = "{9ANIME_URL}"
SEARCH_URL = BASE_URL + "/search"

RE_DUB_STRIPPER = re.compile(r"\s\(Dub\)$")


class NineEpisode(Episode):
    # TODO: automatically switch episode if no stream found! But also start with the most likely stream!
    @cached_property
    async def streams(self) -> List[Stream]:
        stream = await anext(get_stream(Request(await self.host_url)), None)
        if stream:
            return [stream]
        return []

    @cached_property
    async def host_url(self) -> str:
        async with self._req.page as page:
            page: Page
            return await page.evaluate("""document.querySelector("div#player iframe").src""", force_expr=True)


class NineAnime(Anime):
    EPISODE_CLS = NineEpisode

    @cached_property
    async def raw_title(self) -> str:
        return (await self._req.bs).select_one("h2.title").text.strip()

    @cached_property
    async def title(self) -> str:
        return RE_DUB_STRIPPER.sub("", await self.raw_title, 1)

    @cached_property
    async def is_dub(self) -> bool:
        return (await self.raw_title).endswith("(Dub)")

    @property
    async def language(self) -> Language:
        return Language.ENGLISH

    @classmethod
    async def search(cls, query: str, *, language=Language.ENGLISH, dubbed=False) -> Iterator[SearchResult]:
        if language != Language.ENGLISH:
            return

        req = Request(SEARCH_URL, {"keyword": query})
        bs = await req.bs
        container = bs.select_one("div.film-list")
        search_results = container.select("div.item")

        for result in search_results:
            title = result.select_one("a.name").text
            if dubbed != title.endswith("(Dub)"):
                continue

            ep_text_container = result.select_one("div.ep")
            if ep_text_container:
                ep_count = int(ep_text_container.text.split("/", 1)[0][4:])
            else:
                ep_count = 1

            link = result.select_one("a.poster")["href"]
            similarity = get_certainty(query, title)

            anime = cls(Request(link))
            anime._episode_count = ep_count
            yield SearchResult(anime, similarity)

    @cached_property
    async def raw_eps(self) -> List[NineEpisode]:
        async with self._req.page as page:
            page: Page
            episodes = await page.evaluate(
                """Array.from(document.querySelectorAll("div.server:not(.hidden) ul.episodes a")).map(epLink => epLink.href);""", force_expr=True)
            return list(map(lambda url: self.EPISODE_CLS(Request(url)), episodes))

    async def get_episodes(self) -> List[NineEpisode]:
        return await self.raw_eps

    async def get_episode(self, index: int) -> NineEpisode:
        return (await self.raw_eps)[index]


nineanime_pool = UrlPool("9anime", ["https://9anime.vip", "http://9anime.vip"])
DefaultUrlFormatter.add_field("9ANIME_URL", lambda: nineanime_pool.url)

register_source(NineAnime)
