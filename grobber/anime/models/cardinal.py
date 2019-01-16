__all__ = ["Cardinal"]

import asyncio
from typing import Any, AsyncIterator, List, Optional, TYPE_CHECKING

from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.uid import UID
from grobber.utils import get_first
from .anime import Anime
from .episode import Episode
from .stream import Stream
from .. import sources
from ..exceptions import AnimeNotFound

if TYPE_CHECKING:
    from .search_result import SearchResult


class CardinalStream(Stream):
    @cached_property
    async def external(self) -> bool:
        return True

    @cached_property
    async def links(self) -> List[str]:
        pass


class CardinalEpisode(Episode):
    @cached_property
    async def downloaded(self) -> bool:
        return False

    @cached_property
    async def raw_streams(self) -> List[str]:
        return []


class Cardinal(Anime):
    ATTRS = ("anime_uids",)
    EPISODE_CLS = CardinalEpisode

    @cached_property
    async def anime_uids(self) -> List[UID]:
        raise AnimeNotFound(f"No uids for this Cardinal: {self}")

    @cached_property
    async def animes(self) -> List[Anime]:
        uids = await self.anime_uids
        return await asyncio.gather(*(sources.get_anime(uid) for uid in uids))

    async def get_first(self, attr: str) -> Any:
        animes = await self.animes
        return await get_first((getattr(anime, attr) for anime in animes), cancel_running=False)

    @cached_property
    async def title(self) -> str:
        raise AttributeError(f"title must not be changed for Cardinal: {self}")

    @cached_property
    async def language(self) -> Language:
        raise AttributeError(f"language must not be changed for Cardinal: {self}")

    @cached_property
    async def is_dub(self) -> bool:
        raise AttributeError(f"is_dub must not be changed for Cardinal: {self}")

    @cached_property
    async def thumbnail(self) -> Optional[str]:
        return await self.get_first("thumbnail")

    @cached_property
    async def episode_count(self) -> int:
        return await self.get_first("episode_count")

    async def get_episodes(self) -> List[EPISODE_CLS]:
        pass

    async def get_episode(self, index: int) -> EPISODE_CLS:
        pass

    @classmethod
    async def search(cls, query: str, *, dubbed: bool = False, language: Language = Language.ENGLISH) -> AsyncIterator["SearchResult"]:
        raise NotImplementedError
