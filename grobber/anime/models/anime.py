__all__ = ["Anime", "SourceAnime"]

import abc
import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING

from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.stateful import BsonType, Expiring
from grobber.uid import MediaType, UID
from .episode import Episode, SourceEpisode
from ..exceptions import EpisodeNotFound

if TYPE_CHECKING:
    from .search_result import SearchResult

log = logging.getLogger(__name__)


class Anime(abc.ABC):
    def __repr__(self) -> str:
        if hasattr(self, "_media_id"):
            return f"Anime {self._media_id}"
        else:
            return super().__repr__()

    def __str__(self) -> str:
        if hasattr(self, "_title"):
            return self._title
        else:
            return repr(self)

    def __bool__(self) -> bool:
        return True

    @cached_property
    async def media_id(self) -> str:
        return UID.create_media_id(await self.title)

    @abc.abstractmethod
    async def get(self, index: int) -> Episode:
        ...

    @property
    @abc.abstractmethod
    async def uid(self) -> UID:
        ...

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

    @property
    @abc.abstractmethod
    async def episode_count(self) -> int:
        ...

    async def to_dict(self) -> Dict[str, BsonType]:
        uid, media_id, title, thumbnail, episode_count, is_dub, language = await asyncio.gather(
            self.uid, self.media_id, self.title, self.thumbnail, self.episode_count, self.is_dub, self.language
        )

        return {"uid": uid,
                "media_id": media_id,
                "title": title,
                "thumbnail": thumbnail,
                "episodes": episode_count,
                "dubbed": is_dub,
                "language": language.value}


class SourceAnime(Anime, Expiring, abc.ABC):
    EPISODE_CLS = SourceEpisode
    PRELOAD_ATTRS = ("media_id", "is_dub", "language", "title", "thumbnail", "episode_count")

    INCLUDE_CLS = True
    ATTRS = PRELOAD_ATTRS + ("episodes", "last_update")
    CHANGING_ATTRS = ("episode_count",)
    EXPIRE_TIME = 30 * Expiring.MINUTE  # 30 mins should be fine, right?

    _episodes: Dict[int, EPISODE_CLS]

    def __repr__(self) -> str:
        if hasattr(self, "_uid"):
            return self._uid
        else:
            return repr(self._req)

    def __eq__(self, other: "SourceAnime") -> bool:
        return hash(self) == hash(other)

    def __hash__(self) -> int:
        return hash(self._req)

    @property
    def source_id(self) -> str:
        return type(self).__qualname__.lower()

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

    @property
    async def uid(self) -> UID:
        return UID(await self.id)

    @uid.setter
    def uid(self, value: UID):
        # noinspection PyPropertyAccess,PyAttributeOutsideInit
        self.id = value

    @cached_property
    async def id(self) -> str:
        media_id, language, is_dub = await asyncio.gather(self.media_id, self.language, self.is_dub)

        return UID.create(MediaType.ANIME, media_id, self.source_id, language, is_dub)

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
            # noinspection PyTypeChecker
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
        data = await super().to_dict()
        data["updated"] = self.last_update.isoformat()

        return data

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
