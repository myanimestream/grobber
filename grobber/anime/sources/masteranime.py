import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from grobber import utils
from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.request import DefaultUrlFormatter, Request
from grobber.url_pool import UrlPool
from . import register_source
from ..models import Anime, Episode, SearchResult

log = logging.getLogger(__name__)

BASE_URL = "{MASTERANIME_URL}"
SEARCH_URL = BASE_URL + "/api/anime/filter"
ANIME_URL = BASE_URL + "/api/anime/{anime_id}/detailed"
EPISODE_URL = BASE_URL + "/anime/watch/{anime_slug}/{episode}"

masteranime_pool = UrlPool("MasterAnime", ["https://www.masterani.me"])
DefaultUrlFormatter.add_field("MASTERANIME_URL", lambda: masteranime_pool.url)

masteranime_cdn_pool = UrlPool("MasterAnime CDN", ["https://cdn.masterani.me"])


async def get_poster_url(poster_data: Union[Dict[str, Any], str]) -> str:
    base = await masteranime_cdn_pool.url

    if isinstance(poster_data, str):
        path = f"poster/{poster_data}"
    else:
        path = poster_data["path"] + poster_data["file"]

    return f"{base}/{path}"


class MasterEpisode(Episode):
    ATTRS = ("mirror_data",)

    @cached_property
    async def mirror_data(self) -> List[Dict[str, Any]]:
        bs = await self._req.bs
        element = bs.select_one("video-mirrors")

        if not element:
            return []

        return json.loads(element[":mirrors"])

    @cached_property
    async def raw_streams(self) -> List[str]:
        links = []
        for mirror in await self.mirror_data:
            host_data = mirror["host"]
            prefix = host_data["embed_prefix"]
            suffix = host_data["embed_suffix"] or ""
            embed_id = mirror["embed_id"]
            links.append(f"{prefix}{embed_id}{suffix}")

        return links


class MasterAnime(Anime):
    ATTRS = ("anime_id", "anime_slug")
    EPISODE_CLS = MasterEpisode

    @cached_property
    async def info_data(self) -> Dict[str, Any]:
        return (await self._req.json)["info"]

    @cached_property
    async def episode_data(self) -> List[Dict[str, Any]]:
        return (await self._req.json)["episodes"]

    @cached_property
    async def anime_id(self) -> int:
        return (await self.info_data)["id"]

    @cached_property
    async def anime_slug(self) -> str:
        return (await self.info_data)["slug"]

    @cached_property
    async def title(self) -> str:
        return (await self.info_data)["title"]

    @cached_property
    async def thumbnail(self) -> Optional[str]:
        try:
            poster = (await self._req.json)["poster"]
        except KeyError:
            return None
        else:
            return await get_poster_url(poster)

    @cached_property
    async def is_dub(self) -> bool:
        return False

    @cached_property
    async def language(self) -> Language:
        return Language.ENGLISH

    @cached_property
    async def episode_count(self) -> int:
        return len(await self.episode_data)

    @classmethod
    async def search(cls, query: str, *, language=Language.ENGLISH, dubbed=False) -> AsyncIterator[SearchResult]:
        if dubbed or language != Language.ENGLISH:
            return

        # Query limit is 45 characters!!
        req = Request(SEARCH_URL, {"search": query[:45], "order": "relevance_desc"})
        json_data = await req.json

        if not json_data:
            logging.warning("couldn't get json from masteranime")
            return

        for raw_anime in json_data["data"]:
            anime_id = raw_anime["id"]
            title = raw_anime["title"]

            req = Request(utils.format_available(ANIME_URL, anime_id=anime_id))
            anime = cls(req, data=dict(anime_id=anime_id, anime_slug=raw_anime["slug"], title=title, thumbail=get_poster_url(raw_anime["poster"])))

            yield SearchResult(anime, utils.get_certainty(title, query))

    @cached_property
    async def raw_eps(self) -> List[Episode]:
        episodes = []

        slug = await self.anime_slug

        for ep_data in await self.episode_data:
            ep_id = ep_data["info"]["episode"]
            req = Request(utils.format_available(EPISODE_URL, anime_slug=slug, episode=ep_id))
            episodes.append(self.EPISODE_CLS(req))

        return episodes

    async def get_episode(self, index: int) -> Optional[Episode]:
        return (await self.raw_eps)[index]

    async def get_episodes(self) -> List[Episode]:
        return await self.raw_eps


register_source(MasterAnime)
