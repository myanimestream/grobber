import re
from typing import Iterator, List, Tuple

from bs4 import BeautifulSoup

from . import register_source
from .. import utils
from ..decorators import cached_property
from ..models import Anime, Episode, SearchResult, Stream, get_certainty
from ..request import Request
from ..streams import get_stream

SERVERS_TOKEN = 648

BASE_URL = "{9ANIME_URL}"
SEARCH_URL = BASE_URL + "/search"
ANIME_URL = BASE_URL + "/watch/{name}"
EPISODES_URL = BASE_URL + f"/ajax/film/servers/{{anime_code}}?_={SERVERS_TOKEN}"
EPISODE_URL = "https://projectman.ga/api/url"

RE_SPACE = re.compile(r"\s+")
RE_SPECIAL = re.compile(r"[^\w\-]+")
RE_CLEAN = re.compile(r"-+")

RE_DUB_STRIPPER = re.compile(r"\s\(Dub\)$")


def search_anime_page(name: str, dub: bool = False) -> Iterator[Tuple[Request, float]]:
    req = Request(SEARCH_URL, {"keyword": name})
    bs = req.bs
    container = bs.select_one("div.film-list")
    search_results = container.select("div.item")
    for result in search_results:
        title = result.select_one("a.name").text
        if dub != title.endswith("(Dub)"):
            continue
        link = result.select_one("a.poster")["href"]
        similarity = get_certainty(name, title)
        yield Request(link), similarity


class NineEpisode(Episode):
    @cached_property
    def streams(self) -> List[Stream]:
        stream = next(get_stream(Request(self.host_url)), None)
        if stream:
            return [stream]
        return []

    @cached_property
    def finished_req(self) -> Request:
        url = self._req.response.json()["results"]
        return Request(url)

    @cached_property
    def host_url(self) -> str:
        return self.finished_req.response.json()["target"]


class NineAnime(Anime):
    ATTRS = ("anime_id", "anime_code", "server_id")
    EPISODE_CLS = NineEpisode

    @cached_property
    def anime_id(self) -> str:
        return self._req.bs.html["data-ts"]

    @cached_property
    def anime_code(self) -> str:
        return self._req.url.rsplit(".", 1)[-1]

    @cached_property
    def episodes_bs(self) -> BeautifulSoup:
        eps_req = Request(utils.format_available(EPISODES_URL, anime_code=self.anime_code))
        eps_html = eps_req.json["html"]
        return Request.create_soup(eps_html)

    @cached_property
    def server_id(self) -> str:
        return self.episodes_bs.select_one("div.servers span.tab.active")["data-name"]

    @cached_property
    def raw_title(self) -> str:
        return self._req.bs.select_one("h2.title").text

    @cached_property
    def title(self) -> str:
        return RE_DUB_STRIPPER.sub("", self.raw_title, 1)

    @cached_property
    def is_dub(self) -> bool:
        return self.raw_title.endswith("(Dub)")

    @classmethod
    def search(cls, query: str, dub: bool = False) -> Iterator[SearchResult]:
        for req, certainty in search_anime_page(query, dub=dub):
            yield SearchResult(cls(req), certainty)

    @cached_property
    def raw_eps(self) -> List[NineEpisode]:
        bs = self.episodes_bs

        eps = bs.select("div.server.active ul.episodes.active li")
        episodes = []
        for ep in eps:
            ep_id = ep.a["data-id"]
            params = {"ts": self.anime_id, "id": ep_id, "server": self.server_id}
            req = Request(EPISODE_URL, params)
            episodes.append(self.EPISODE_CLS(req))
        return episodes

    def get_episodes(self) -> List[NineEpisode]:
        return self.raw_eps

    def get_episode(self, index: int) -> NineEpisode:
        return self.raw_eps[index]


register_source(NineAnime)
