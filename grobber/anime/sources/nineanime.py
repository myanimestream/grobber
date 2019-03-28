import logging
import re
from typing import Iterator, List, Optional, cast

import yarl
from pyppeteer.page import Page

from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.request import DefaultUrlFormatter, Request
from grobber.url_pool import UrlPool
from grobber.utils import get_certainty
from . import register_source
from ..models import SearchResult, SourceAnime, SourceEpisode

log = logging.getLogger(__name__)

BASE_URL = "{9ANIME_URL}"
SEARCH_URL = BASE_URL + "/search"

RE_DUB_STRIPPER = re.compile(r"\s\(Dub\)$")


class NineEpisode(SourceEpisode):
    @cached_property
    async def raw_streams(self) -> List[str]:
        raw_streams = []
        async with self._req.page as page:
            page = cast(Page, page)
            await page.waitFor("div#player .cover")
            await page.evaluate("""document.querySelector("div#player .cover").click();""")

            episode_base = await page.evaluate("""document.querySelector("ul.episodes a.active").getAttribute("data-base");""")
            servers = await page.querySelectorAll(f"ul.episodes a[data-base=\"{episode_base}\"]")

            for server in servers:
                try:
                    await page.evaluate("""(el) => el.click()""", server)
                    await page.bringToFront()
                    await page.waitFor("div#player iframe")
                    src = await page.evaluate("""document.querySelector("div#player iframe").src;""", force_expr=True)
                    raw_streams.append(src)
                except Exception as e:
                    log.exception("Couldn't get src of server")
                finally:
                    await server.dispose()

        log.debug(f"extracted {len(raw_streams)} raw streams from page")
        return raw_streams


class NineAnime(SourceAnime):
    EPISODE_CLS = NineEpisode

    @cached_property
    async def raw_title(self) -> str:
        return (await self._req.bs).select_one("h2.title").text.strip()

    @cached_property
    async def title(self) -> str:
        return RE_DUB_STRIPPER.sub("", await self.raw_title, 1)

    @cached_property
    async def thumbnail(self) -> Optional[str]:
        return (await self._req.bs).select_one("div.thumb img")["src"]

    @cached_property
    async def is_dub(self) -> bool:
        return (await self.raw_title).endswith("(Dub)")

    @cached_property
    async def language(self) -> Language:
        return Language.ENGLISH

    @classmethod
    async def search(cls, query: str, *, language=Language.ENGLISH, dubbed=False) -> Iterator[SearchResult]:
        if language != Language.ENGLISH:
            return

        for _ in range(5):
            req = Request(SEARCH_URL, {"keyword": query}, use_proxy=True)
            bs = await req.bs
            container = bs.select_one("div.film-list")

            if container:
                break

            log.debug(f"trying again {req._text}")
            req.reload()
        else:
            log.warning(f"{cls} Couldn't get search results, retries exceeded!")
            return

        search_results = container.select("div.item")

        for result in search_results:
            raw_title = result.select_one("a.name").text
            if dubbed != raw_title.endswith("(Dub)"):
                continue

            title = RE_DUB_STRIPPER.sub("", raw_title, 1)

            ep_text_container = result.select_one("div.ep")
            if ep_text_container:
                ep_text = ep_text_container.text.split("/", 1)[0].strip()[3:]

                if ep_text.isnumeric():
                    ep_count = int(ep_text)
                else:
                    log.warning(f"{cls} {req} Couldn't tell episode count {ep_text}")
                    ep_count = 0
            else:
                ep_count = 1

            link = yarl.URL(result.select_one("a.poster")["href"])
            thumbnail = result.select_one("a.poster img")["src"]
            similarity = get_certainty(query, title)

            anime = cls(Request(BASE_URL + link.path), data=dict(raw_title=raw_title,
                                                                 title=title,
                                                                 is_dub=dubbed,
                                                                 episode_count=ep_count,
                                                                 thumbnail=thumbnail))
            yield SearchResult(anime, similarity)

    @cached_property
    async def raw_eps(self) -> List[NineEpisode]:
        async with self._req.page as page:
            page = cast(Page, page)
            episodes = await page.evaluate(
                """Array.from(document.querySelectorAll("div.server:not(.hidden) ul.episodes a")).map(epLink => epLink.href);""", force_expr=True)

            return list(map(lambda url: self.EPISODE_CLS(Request(BASE_URL + yarl.URL(url).path)), episodes))

    async def get_episodes(self) -> List[NineEpisode]:
        return await self.raw_eps

    async def get_episode(self, index: int) -> NineEpisode:
        return (await self.raw_eps)[index]


nineanime_pool = UrlPool("9Anime", ["https://9anime.to", "https://www2.9anime.to"])
DefaultUrlFormatter.add_field("9ANIME_URL", lambda: nineanime_pool.url)

register_source(NineAnime)
