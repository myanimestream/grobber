import asyncio
import logging
import re
from typing import AsyncIterator, Dict, List, Optional, Pattern

import math

from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.request import DefaultUrlFormatter, Request
from grobber.url_pool import UrlPool
from grobber.utils import add_http_scheme, get_certainty
from . import register_source
from ..models import SearchResult, SourceAnime, SourceEpisode

log = logging.getLogger(__name__)

BASE_URL = "{GOGOANIME_URL}"
SEARCH_URL = BASE_URL + "//search.html"
EPISODE_LIST_URL = BASE_URL + "//load-list-episode"
ANIME_URL = BASE_URL + "/category/{name}"

RE_SPACE = re.compile(r"\s+")
RE_SPECIAL = re.compile(r"[^\w\-]+")
RE_CLEAN = re.compile(r"-+")

RE_DUB_STRIPPER = re.compile(r"\s\(Dub\)$")

RE_NOT_FOUND = re.compile(r"<h1 class=\"entry-title\">Page not found</h1>")
RE_EPISODE_URL_PARSER: Pattern = re.compile(r"(?P<prefix>[^/]+-episode-)(?P<episode>.+)$")


async def is_not_found_page(req: Request) -> bool:
    return bool(RE_NOT_FOUND.search(await req.text))


def get_potential_page_name(name: str) -> str:
    page_name = name.lower()
    page_name = RE_SPACE.sub("-", page_name)
    page_name = RE_SPECIAL.sub("", page_name)
    page_name = RE_CLEAN.sub("-", page_name)
    return page_name


class GogoEpisode(SourceEpisode):
    @cached_property
    async def raw_streams(self) -> List[str]:
        bs = await self._req.bs
        links = bs.select("div.anime_muti_link a")

        streams = []
        for link in links:
            streams.append(add_http_scheme(link["data-video"]))

        return streams


class GogoAnime(SourceAnime):
    ATTRS = ("anime_id", "raw_title")
    EPISODE_CLS = GogoEpisode

    @cached_property
    async def anime_id(self) -> str:
        return (await self._req.bs).find(id="movie_id")["value"]

    @cached_property
    async def raw_title(self) -> str:
        return (await self._req.bs).select_one("div.anime_info_body_bg h1").text

    @cached_property
    async def title(self) -> str:
        return RE_DUB_STRIPPER.sub("", await self.raw_title, 1)

    @cached_property
    async def thumbnail(self) -> Optional[str]:
        return None

    @cached_property
    async def is_dub(self) -> bool:
        return (await self.raw_title).endswith("(Dub)")

    @cached_property
    async def language(self) -> Language:
        return Language.ENGLISH

    @cached_property
    async def episode_count(self) -> int:
        holder = (await self._req.bs).select_one("#episode_page a.active")
        if not holder:
            return 0

        last_ep_text = holder["ep_end"]
        if last_ep_text.isnumeric():
            return int(last_ep_text)

        log.info(f"Last episode label isn't numeric: {last_ep_text}")

        try:
            # I'm totally assuming that decimal values are always .5... Try to stop me
            return int(math.ceil(float(last_ep_text)))
        except ValueError:
            raise ValueError(f"Couldn't understand last episode label for {self}: \"{last_ep_text}\"")

    @classmethod
    async def search(cls, query: str, *, language=Language.ENGLISH, dubbed=False) -> AsyncIterator[SearchResult]:
        if language != Language.ENGLISH:
            return

        req = Request(SEARCH_URL, {"keyword": query})
        bs = await req.bs
        container = bs.select_one("ul.items")
        if not container:
            return

        search_results = container.find_all("li")

        for result in search_results:
            image_link = result.find("a")
            raw_title = image_link["title"]
            if dubbed != raw_title.endswith("(Dub)"):
                continue

            title = RE_DUB_STRIPPER.sub("", raw_title, 1)

            thumbnail = image_link.find("img")["src"]

            link = BASE_URL + image_link["href"]
            anime = cls(Request(link), data=dict(raw_title=raw_title, title=title, is_dub=dubbed, thumbnail=thumbnail))

            similarity = get_certainty(query, title)
            yield SearchResult(anime, similarity)

    @cached_property
    async def raw_eps(self) -> Dict[int, EPISODE_CLS]:
        anime_id, episode_count = await asyncio.gather(self.anime_id, self.episode_count)

        episode_req = Request(EPISODE_LIST_URL, {"id": anime_id, "ep_start": 0, "ep_end": episode_count})
        if await is_not_found_page(episode_req):
            # you might think this check is stupid but you wouldn't believe what a headache this has already caused me
            # the gogoanime 404 page also lists episodes just like the real page does, only they are from "recently updated"
            # shows so it would show completely unrelated episodes... So please PRAISE this check, thanks!
            raise ValueError(f"hit not found page when loading list episode for {self!r}: {episode_req}")

        episode_links = (await episode_req.bs).find_all("li")
        episodes: Dict[int, GogoEpisode] = {}
        for episode_link in reversed(episode_links):
            href = episode_link.a["href"].lstrip()
            match = RE_EPISODE_URL_PARSER.search(href)
            if not match:
                log.info(f"{self!r} Couldn't parse episode url {href}, moving on")
                continue

            episode_number_str = match["episode"]

            try:
                episode_number = int(episode_number_str)
            except ValueError:
                log.info(f"{self!r} couldn't parse episode number \"{episode_number_str!r}\", moving on")
                continue

            req = Request(BASE_URL + href)
            episodes[episode_number - 1] = self.EPISODE_CLS(req)

        return episodes

    async def get_episode(self, index: int) -> Optional[GogoEpisode]:
        page_name = get_potential_page_name(await self.title)
        ep_req = Request(f"{BASE_URL}/{page_name}-episode-{index + 1}")
        log.debug(f"Trying to predict episode link {ep_req}")
        if await is_not_found_page(ep_req):
            log.debug("-> Prediction Invalid, manually fetching...")
            return (await self.raw_eps)[index]
        else:
            log.debug("-> Prediction successful")
            return self.EPISODE_CLS(ep_req)

    async def get_episodes(self) -> Dict[int, GogoEpisode]:
        return await self.raw_eps


gogoanime_pool = UrlPool("GogoAnime", ["https://gogoanime.io", "http://gogoanime.io"])
DefaultUrlFormatter.add_field("GOGOANIME_URL", lambda: gogoanime_pool.url)
DefaultUrlFormatter.use_proxy("GOGOANIME_URL")

register_source(GogoAnime)
