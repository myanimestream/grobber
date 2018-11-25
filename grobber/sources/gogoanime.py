import logging
import math
import re
from operator import attrgetter
from typing import Iterator, List, Optional, Tuple

from . import register_source
from ..decorators import cached_property
from ..models import Anime, Episode, SearchResult, Stream, get_certainty
from ..request import Request
from ..streams import get_stream
from ..utils import add_http_scheme

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


def is_not_found_page(req: Request):
    return bool(RE_NOT_FOUND.search(req.text))


def get_potential_page_name(name: str) -> str:
    page_name = name.lower()
    page_name = RE_SPACE.sub("-", page_name)
    page_name = RE_SPECIAL.sub("", page_name)
    page_name = RE_CLEAN.sub("-", page_name)
    return page_name


def search_anime_page(name: str, dub: bool = False) -> Iterator[Tuple[Request, float]]:
    req = Request(SEARCH_URL, {"keyword": name})
    bs = req.bs
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
        similarity = get_certainty(name, title)
        yield Request(link), similarity


class GogoEpisode(Episode):
    @cached_property
    def streams(self) -> List[Stream]:
        streams = []
        links = self._req.bs.select("div.anime_muti_link a")
        for link in links:
            stream = next(get_stream(Request(add_http_scheme(link["data-video"]))), None)
            if stream:
                streams.append(stream)
        streams.sort(key=attrgetter("PRIORITY"), reverse=True)
        return streams

    @cached_property
    def host_url(self) -> str:
        return add_http_scheme(self._req.bs.find("iframe")["src"], _scheme="https")


class GogoAnime(Anime):
    ATTRS = ("anime_id", "raw_title")
    EPISODE_CLS = GogoEpisode

    @cached_property
    def anime_id(self) -> str:
        return self._req.bs.find(id="movie_id")["value"]

    @cached_property
    def raw_title(self) -> str:
        return self._req.bs.select_one("div.anime_info_body_bg h1").text

    @cached_property
    def title(self) -> str:
        return RE_DUB_STRIPPER.sub("", self.raw_title, 1)

    @cached_property
    def is_dub(self) -> bool:
        return self.raw_title.endswith("(Dub)")

    @cached_property
    def episode_count(self) -> int:
        holder = self._req.bs.select_one("#episode_page a.active")
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
    def search(cls, query: str, dub: bool = False) -> Iterator[SearchResult]:
        for req, certainty in search_anime_page(query, dub=dub):
            yield SearchResult(cls(req), certainty)

    @cached_property
    def raw_eps(self) -> List[GogoEpisode]:
        episode_req = Request(EPISODE_LIST_URL, {"id": self.anime_id, "ep_start": 0, "ep_end": self.episode_count})
        episode_links = episode_req.bs.find_all("li")
        episodes = []
        for episode_link in reversed(episode_links):
            episodes.append(self.EPISODE_CLS(Request(BASE_URL + episode_link.a["href"].lstrip())))
        return episodes

    def get_episode(self, index: int) -> Optional[GogoEpisode]:
        page_name = get_potential_page_name(self.title)
        ep_req = Request(f"{BASE_URL}/{page_name}-episode-{index + 1}")
        log.debug(f"Trying to predict episode link {ep_req}")
        if is_not_found_page(ep_req):
            log.debug("-> Prediction Invalid, manually fetching...")
            return self.raw_eps[index]
        else:
            return self.EPISODE_CLS(ep_req)

    def get_episodes(self) -> List[GogoEpisode]:
        return self.raw_eps


register_source(GogoAnime)
