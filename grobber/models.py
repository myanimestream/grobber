import abc
import logging
import re
import sys
from collections import namedtuple
from datetime import datetime
from difflib import SequenceMatcher
from functools import partial
from itertools import groupby
from operator import attrgetter
from typing import Any, Dict, Iterator, List, MutableSequence, NewType, Optional, Union

from quart.routing import BaseConverter

from .decorators import cached_property
from .exceptions import EpisodeNotFound
from .request import Request
from .stateful import BsonType, Expiring
from .utils import thread_pool, wait_for_first

log = logging.getLogger(__name__)

UID = NewType("UID", str)


class UIDConverter(BaseConverter):
    def to_python(self, value):
        return UID(value)

    def to_url(self, value):
        return super().to_url(value)


RE_UID_CLEANER = re.compile(r"[^a-z0-9一-龯]+")


def get_certainty(a: str, b: str) -> float:
    return round(SequenceMatcher(a=a, b=b).ratio(), 2)


class SearchResult(namedtuple("SearchResult", ("anime", "certainty"))):
    def to_dict(self):
        return {"anime": self.anime.to_dict(),
                "certainty": self.certainty}


VIDEO_MIME_TYPES = ("video/webm", "video/ogg", "video/mp4")


class Stream(Expiring, abc.ABC):
    INCLUDE_CLS = True
    ATTRS = ("links", "poster")
    CHANGING_ATTRS = ("links",)
    EXPIRE_TIME = Expiring.HOUR

    PRIORITY = 1

    HOST = None

    def __repr__(self) -> str:
        return f"{type(self).__name__} Stream: {self._req}"

    def __iter__(self) -> Iterator[str]:
        return iter(self.links)

    @classmethod
    def can_handle(cls, req: Request) -> bool:
        return req.yarl.host.lstrip("www.") == cls.HOST

    @property
    @abc.abstractmethod
    def links(self) -> List[str]:
        ...

    @cached_property
    def poster(self) -> Optional[str]:
        return None

    @cached_property
    def working(self) -> bool:
        return len(self.links) > 0

    @property
    def working_self(self) -> Optional["Stream"]:
        if self.working:
            return self
        else:
            return None

    @staticmethod
    def get_successful_links(sources: Union[Request, MutableSequence[Request]]) -> List[str]:
        if isinstance(sources, Request):
            sources = [sources]

        for source in sources:
            source.request_kwargs["allow_redirects"] = True

        all(thread_pool.map(attrgetter("head_success"), sources))

        urls = []
        for source in sources:
            if source.head_success:
                content_type = source.head_response.headers.get("content-type")
                if not content_type:
                    log.debug(f"No content type for {source}")
                    continue
                if content_type.startswith(VIDEO_MIME_TYPES):
                    log.debug(f"Accepting {source}")
                    urls.append(source.url)
            else:
                log.debug(f"{source} didn't make it!")

        return urls

    def to_dict(self) -> Dict[str, BsonType]:
        return {"type": type(self).__name__,
                "url": self._req.url,
                "links": self.links,
                "poster": self.poster,
                "updated": self.last_update.isoformat()}


class Episode(Expiring, abc.ABC):
    ATTRS = ("streams", "host_url", "stream", "poster", "host_url")
    CHANGING_ATTRS = ATTRS
    EXPIRE_TIME = 6 * Expiring.HOUR

    def __init__(self, req: Request):
        super().__init__(req)

    def __repr__(self) -> str:
        return f"{type(self).__name__} Ep.: {repr(self._req)}"

    @property
    def dirty(self) -> bool:
        if self._dirty:
            return True
        else:
            if hasattr(self, "_streams"):
                return any(stream.dirty for stream in self._streams)
            return False

    @dirty.setter
    def dirty(self, value: bool):
        self._dirty = value
        if hasattr(self, "_streams"):
            for stream in self._streams:
                stream.dirty = value

    @property
    @abc.abstractmethod
    def streams(self) -> List[Stream]:
        ...

    @cached_property
    def stream(self) -> Optional[Stream]:
        log.debug(f"{self} Searching for working stream...")
        for priority, streams in groupby(self.streams, attrgetter("PRIORITY")):
            streams = list(streams)
            log.debug(f"Looking at {len(streams)} stream(s) with priority {priority}")
            items = [partial(attrgetter("working_self"), stream) for stream in self.streams]
            working_stream = wait_for_first(items)
            if working_stream:
                log.debug(f"Found working stream: {working_stream}")
                return working_stream

        log.debug(f"No working stream for {self}")

    @cached_property
    def poster(self) -> Optional[str]:
        log.debug("searching for poster")
        items = [partial(attrgetter("poster"), stream) for stream in self.streams]
        return wait_for_first(items)

    @property
    @abc.abstractmethod
    def host_url(self) -> str:
        ...

    def serialise_special(self, key: str, value: Any) -> BsonType:
        if key == "streams":
            return [stream.state for stream in value if getattr(stream, "_links", False) or getattr(stream, "_poster", False)]
        elif key == "stream":
            return value.state

    @classmethod
    def get_stream(cls, data: BsonType) -> Optional[Stream]:
        m, c = data["cls"].rsplit(".", 1)
        module = sys.modules.get(m)
        if module:
            stream_cls = getattr(module, c)
            return stream_cls.from_state(data)

    @classmethod
    def deserialise_special(cls, key: str, value: BsonType) -> Any:
        if key == "streams":
            streams = []
            for stream in value:
                streams.append(cls.get_stream(stream))
            return streams
        elif key == "stream":
            return cls.get_stream(value)

    def to_dict(self) -> Dict[str, BsonType]:
        return {"embed": self.host_url,
                "stream": self.stream.to_dict() if self.stream else None,
                "poster": self.poster,
                "updated": self.last_update.isoformat()}


class Anime(Expiring, abc.ABC):
    EPISODE_CLS = Episode

    INCLUDE_CLS = True
    ATTRS = ("id", "is_dub", "title", "episode_count", "episodes", "last_update")
    CHANGING_ATTRS = ("episode_count",)
    EXPIRE_TIME = 30 * Expiring.MINUTE  # 30 mins should be fine, right?

    _episodes: Dict[int, EPISODE_CLS]

    def __init__(self, req: Request):
        super().__init__(req)
        self._dirty = False
        self._last_update = datetime.now()

    def __getitem__(self, item: int) -> EPISODE_CLS:
        return self.get(item)

    def __bool__(self) -> bool:
        return True

    def __len__(self) -> int:
        return self.episode_count

    def __iter__(self) -> Iterator[EPISODE_CLS]:
        return iter(self.episodes.values())

    def __repr__(self) -> str:
        return self.uid

    def __str__(self) -> str:
        return self.title

    def __eq__(self, other: "Anime") -> bool:
        return self.uid == other.uid

    def __hash__(self) -> int:
        if hasattr(self, "_uid") or hasattr(self._req, "_response"):
            return hash(self.uid)
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
    def uid(self) -> UID:
        name = RE_UID_CLEANER.sub("", type(self).__name__.lower())
        anime = RE_UID_CLEANER.sub("", self.title.lower())
        dub = "-dub" if self.is_dub else ""
        return UID(f"{name}-{anime}{dub}")

    @property
    def id(self) -> UID:
        return self.uid

    @id.setter
    def id(self, value: UID):
        self._uid = value

    @property
    @abc.abstractmethod
    def is_dub(self) -> False:
        ...

    @property
    @abc.abstractmethod
    def title(self) -> str:
        ...

    @cached_property
    def episode_count(self) -> int:
        return len(self.get_episodes())

    @property
    def episodes(self) -> Dict[int, EPISODE_CLS]:
        if hasattr(self, "_episodes"):
            if len(self._episodes) != self.episode_count:
                log.info(f"{self} doesn't have all episodes. updating!")
                for i in range(self.episode_count):
                    if i not in self._episodes:
                        self._episodes[i] = self.get_episode(i)
        else:
            eps = self.get_episodes()
            self._episodes = dict(enumerate(eps))

        return self._episodes

    def get(self, index: int) -> EPISODE_CLS:
        if hasattr(self, "_episodes"):
            ep = self._episodes.get(index)
            if ep is not None:
                return ep
        try:
            return self.episodes[index]
        except KeyError:
            raise EpisodeNotFound(index, self.episode_count)

    @abc.abstractmethod
    def get_episodes(self) -> List[EPISODE_CLS]:
        ...

    @abc.abstractmethod
    def get_episode(self, index: int) -> EPISODE_CLS:
        ...

    def to_dict(self) -> Dict[str, BsonType]:
        return {"uid": self.uid,
                "title": self.title,
                "episodes": self.episode_count,
                "dub": self.is_dub,
                "updated": self.last_update.isoformat()}

    @classmethod
    @abc.abstractmethod
    def search(cls, query: str, dub: bool = False) -> Iterator[SearchResult]:
        ...

    def serialise_special(self, key: str, value: Any) -> BsonType:
        if key == "episodes":
            return {str(i): ep.state for i, ep in value.items()}

    @classmethod
    def deserialise_special(cls, key: str, value: BsonType) -> Any:
        if key == "episodes":
            return {int(i): cls.EPISODE_CLS.from_state(ep) for i, ep in value.items()}
