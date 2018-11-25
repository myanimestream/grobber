import json
import logging
from operator import attrgetter
from typing import Any, Dict, Iterator, List, Optional

from . import register_source
from .. import utils
from ..decorators import cached_property
from ..models import Anime, Episode, SearchResult, Stream, get_certainty
from ..request import Request
from ..streams import get_stream

log = logging.getLogger(__name__)

BASE_URL = "{MASTERANIME_URL}"
SEARCH_URL = BASE_URL + "/api/anime/filter"
ANIME_URL = BASE_URL + "/api/anime/{anime_id}/detailed"
EPISODE_URL = BASE_URL + "/anime/watch/{anime_slug}/{episode}"


class MasterEpisode(Episode):
    ATTRS = ("mirror_data", "mirror_links")

    @cached_property
    def mirror_data(self) -> List[Dict[str, Any]]:
        bs = self._req.bs
        element = bs.select_one("video-mirrors")

        if not element:
            return []

        return json.loads(element[":mirrors"])

    @cached_property
    def mirror_links(self) -> List[str]:
        links = []
        for mirror in self.mirror_data:
            host_data = mirror["host"]
            prefix = host_data["embed_prefix"]
            suffix = host_data["embed_suffix"] or ""
            embed_id = mirror["embed_id"]
            links.append(f"{prefix}{embed_id}{suffix}")

        return links

    @cached_property
    def streams(self) -> List[Stream]:
        streams = []
        for link in self.mirror_links:
            stream = next(get_stream(Request(link)), None)
            if stream:
                streams.append(stream)

        streams.sort(key=attrgetter("PRIORITY"), reverse=True)
        return streams

    @cached_property
    def host_url(self) -> str:
        if self.mirror_links:
            return self.mirror_links[0]
        else:
            return self._req.url


class MasterAnime(Anime):
    ATTRS = ("anime_id", "anime_slug")
    EPISODE_CLS = MasterEpisode

    @cached_property
    def info_data(self) -> Dict[str, Any]:
        return self._req.json["info"]

    @cached_property
    def episode_data(self) -> List[Dict[str, Any]]:
        return self._req.json["episodes"]

    @cached_property
    def anime_id(self) -> int:
        return self.info_data["id"]

    @cached_property
    def anime_slug(self) -> str:
        return self.info_data["slug"]

    @cached_property
    def title(self) -> str:
        return self.info_data["title"]

    @cached_property
    def is_dub(self) -> bool:
        return False

    @cached_property
    def episode_count(self) -> int:
        return self.info_data["episode_count"]

    @classmethod
    def search(cls, query: str, dub: bool = False) -> Iterator[SearchResult]:
        if dub:
            log.debug("dubbed not supported")
            return

        req = Request(SEARCH_URL, {"search": query, "order": "relevance_desc"})

        for raw_anime in req.json["data"]:
            anime_id = raw_anime["id"]
            title = raw_anime["title"]

            req = Request(utils.format_available(ANIME_URL, anime_id=anime_id))
            anime = cls(req)

            anime._anime_id = anime_id
            anime._anime_slug = raw_anime["slug"]
            anime._title = title
            anime._episode_count = raw_anime["episode_count"]

            yield SearchResult(anime, get_certainty(title, query))

    @cached_property
    def raw_eps(self) -> List[Episode]:
        episodes = []

        for ep_data in self.episode_data:
            ep_id = ep_data["info"]["episode"]
            req = Request(utils.format_available(EPISODE_URL, anime_slug=self.anime_slug, episode=ep_id))
            episodes.append(self.EPISODE_CLS(req))

        return episodes

    def get_episode(self, index: int) -> Optional[Episode]:
        return self.raw_eps[index]

    def get_episodes(self) -> List[Episode]:
        return self.raw_eps


register_source(MasterAnime)
