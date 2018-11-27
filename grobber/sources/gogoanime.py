import logging
import math
import re
from operator import attrgetter
from typing import AsyncIterator, List, Optional

from . import register_source
from ..decorators import cached_property
from ..models import Anime, Episode, SearchResult, Stream, get_certainty
from ..request import Request
from ..streams import get_stream
from ..utils import add_http_scheme, anext

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


async def is_not_found_page(req: Request) -> bool:
    return bool(RE_NOT_FOUND.search(await req.text))


def get_potential_page_name(name: str) -> str:
    page_name = name.lower()
    page_name = RE_SPACE.sub("-", page_name)
    page_name = RE_SPECIAL.sub("", page_name)
    page_name = RE_CLEAN.sub("-", page_name)
    return page_name


class GogoEpisode(Episode):
    @cached_property
    async def streams(self) -> List[Stream]:
        streams = []
        bs = await self._req.bs
        links = bs.select("div.anime_muti_link a")
        for link in links:
            stream = await anext(get_stream(Request(add_http_scheme(link["data-video"]))), None)
            if stream:
                streams.append(stream)

        streams.sort(key=attrgetter("PRIORITY"), reverse=True)
        return streams

    @cached_property
    async def host_url(self) -> str:
        return add_http_scheme((await self._req.bs).find("iframe")["src"], _scheme="https")


class GogoAnime(Anime):
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
    async def is_dub(self) -> bool:
        return (await self.raw_title).endswith("(Dub)")

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
    async def search(cls, query: str, dub: bool = False) -> AsyncIterator[SearchResult]:
        req = Request(SEARCH_URL, {"keyword": query})
        bs = await req.bs
        container = bs.select_one("ul.items")
        if not container:
            return

        search_results = container.find_all("li")

        for result in search_results:
            image_link = result.find("a")
            title = image_link["title"]
            if dub != title.endswith("(Dub)"):
                continue

            link = BASE_URL + image_link["href"]
            similarity = get_certainty(query, title)
            yield SearchResult(cls(Request(link)), similarity)

    @cached_property
    async def raw_eps(self) -> List[GogoEpisode]:
        episode_req = Request(EPISODE_LIST_URL, {"id": await self.anime_id, "ep_start": 0, "ep_end": await self.episode_count})
        episode_links = (await episode_req.bs).find_all("li")
        episodes = []
        for episode_link in reversed(episode_links):
            episodes.append(self.EPISODE_CLS(Request(BASE_URL + episode_link.a["href"].lstrip())))

        return episodes

    async def get_episode(self, index: int) -> Optional[GogoEpisode]:
        page_name = get_potential_page_name(await self.title)
        ep_req = Request(f"{BASE_URL}/{page_name}-episode-{index + 1}")
        log.debug(f"Trying to predict episode link {ep_req}")
        if is_not_found_page(ep_req):
            log.debug("-> Prediction Invalid, manually fetching...")
            return (await self.raw_eps)[index]
        else:
            return self.EPISODE_CLS(ep_req)

    async def get_episodes(self) -> List[GogoEpisode]:
        return await self.raw_eps


register_source(GogoAnime)
