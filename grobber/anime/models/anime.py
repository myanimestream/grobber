__all__ = ["Anime"]

import abc
import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING

from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.stateful import BsonType, Expiring
from grobber.uid import MediaType, UID
from .episode import Episode
from ..exceptions import EpisodeNotFound

if TYPE_CHECKING:
    from .search_result import SearchResult

log = logging.getLogger(__name__)


class Anime(Expiring, abc.ABC):
    EPISODE_CLS = Episode

    INCLUDE_CLS = True
    ATTRS = ("id", "is_dub", "language", "title", "thumbnail", "episode_count", "episodes", "last_update")
    CHANGING_ATTRS = ("episode_count",)
    EXPIRE_TIME = 30 * Expiring.MINUTE  # 30 mins should be fine, right?

    _episodes: Dict[int, EPISODE_CLS]

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        if hasattr(self, "_uid"):
            return self._uid
        else:
            return repr(self._req)

    def __str__(self) -> str:
        if hasattr(self, "_title"):
            return self._title
        else:
            return repr(self)

    def __eq__(self, other: "Anime") -> bool:
        return hash(self) == hash(other)

    def __hash__(self) -> int:
        if hasattr(self, "_uid"):
            return hash(self._uid)
        return hash(self._req)

    @property
    def dirty(self) -> bool:
        if self._dirty:
            return True
        else:
            if hasattr(self, "_episodes"):
                return any(ep.dirty for ep in self._episodes.values())
            return False

    @dirty.setter
    def dirty(self, value: bool):
        self._dirty = value
        if hasattr(self, "_episodes"):
            for ep in self._episodes.values():
                ep.dirty = value

    @cached_property
    async def uid(self) -> UID:
        source = type(self).__qualname__.lower()
        anime_id = UID.create_media_id(await self.title)

        language, is_dub = await asyncio.gather(self.language, self.is_dub)

        return UID.create(MediaType.ANIME, anime_id, source, language, is_dub)

    @property
    async def id(self) -> UID:
        return await self.uid

    @id.setter
    def id(self, value: UID):
        self._uid = value

    @property
    @abc.abstractmethod
    async def is_dub(self) -> bool:
        ...

    @property
    @abc.abstractmethod
    async def language(self) -> Language:
        ...

    @property
    @abc.abstractmethod
    async def title(self) -> str:
        ...

    @property
    @abc.abstractmethod
    async def thumbnail(self) -> Optional[str]:
        ...

    @cached_property
    async def episode_count(self) -> int:
        return len(await self.get_episodes())

    @property
    async def episodes(self) -> Dict[int, EPISODE_CLS]:
        if hasattr(self, "_episodes"):
            if len(self._episodes) != await self.episode_count:
                log.info(f"{self} doesn't have all episodes. updating!")

                for i in range(await self.episode_count):
                    if i not in self._episodes:
                        self._episodes[i] = await self.get_episode(i)
        else:
            eps = await self.get_episodes()
            self._episodes = dict(enumerate(eps))

        return self._episodes

    async def get(self, index: int) -> EPISODE_CLS:
        if hasattr(self, "_episodes"):
            ep = self._episodes.get(index)
            if ep is not None:
                return ep
        else:
            self._episodes = {}

        try:
            episode = self._episodes[index] = await self.get_episode(index)
        except KeyError:
            raise EpisodeNotFound(index, await self.episode_count)
        else:
            return episode

    @abc.abstractmethod
    async def get_episodes(self) -> List[EPISODE_CLS]:
        ...

    @abc.abstractmethod
    async def get_episode(self, index: int) -> EPISODE_CLS:
        ...

    async def to_dict(self) -> Dict[str, BsonType]:
        uid, title, thumbnail, episode_count, is_dub, language = await asyncio.gather(
            self.uid, self.title, self.thumbnail, self.episode_count, self.is_dub, self.language)

        return {"uid": uid,
                "title": title,
                "thumbnail": thumbnail,
                "episodes": episode_count,
                "dubbed": is_dub,
                "language": language.value,
                "updated": self.last_update.isoformat()}

    @classmethod
    @abc.abstractmethod
    async def search(cls, query: str, *, dubbed: bool = False, language: Language = Language.ENGLISH) -> AsyncIterator["SearchResult"]:
        ...

    def serialise_special(self, key: str, value: Any) -> BsonType:
        if key == "episodes":
            return {str(i): ep.state for i, ep in value.items()}
        elif key == "language":
            return value.value

        return super().serialise_special(key, value)

    @classmethod
    def deserialise_special(cls, key: str, value: BsonType) -> Any:
        if key == "episodes":
            return {int(i): cls.EPISODE_CLS.from_state(ep) for i, ep in value.items()}
        elif key == "language":
            return Language(value)

        return super().deserialise_special(key, value)
