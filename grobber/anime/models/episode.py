__all__ = ["Episode"]

import abc
import asyncio
import logging
from itertools import groupby
from operator import attrgetter
from typing import Any, Dict, List, Optional, TypeVar

from grobber.decorators import cached_property
from grobber.request import Request
from grobber.stateful import BsonType, Expiring
from grobber.utils import anext, get_first
from .stream import Stream
from ..exceptions import StreamNotFound

log = logging.getLogger(__name__)

T = TypeVar("T")


class Episode(Expiring, abc.ABC):
    ATTRS = ("stream", "host_url", "raw_streams", "streams", "poster", "host_url")
    CHANGING_ATTRS = ATTRS
    EXPIRE_TIME = 6 * Expiring.HOUR

    def __init__(self, req: Request):
        super().__init__(req)

    def __repr__(self) -> str:
        return f"{type(self).__qualname__} Ep.: {repr(self._req)}"

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
    async def raw_streams(self) -> List[str]:
        ...

    @cached_property
    async def streams(self) -> List[Stream]:
        from ..streams import get_stream

        links = await self.raw_streams

        streams = list(filter(None, await asyncio.gather(*(anext(get_stream(Request(link))) for link in links))))

        streams.sort(key=attrgetter("PRIORITY"), reverse=True)
        return streams

    @cached_property
    async def sources(self) -> List[str]:
        sources = []
        streams = await self.streams
        stream_links = await asyncio.gather(*(stream.links for stream in streams))

        for links in stream_links:
            sources.extend(links)

        return sources

    @cached_property
    async def stream(self) -> Optional[Stream]:
        log.debug(f"{self} Searching for working stream...")

        all_streams = await self.streams
        all_streams.sort(key=attrgetter("PRIORITY"), reverse=True)

        for priority, streams in groupby(all_streams, attrgetter("PRIORITY")):
            streams = list(streams)
            log.info(f"Looking at {len(streams)} stream(s) with priority {priority}")

            working_stream = await get_first([stream.working_external_self for stream in streams])
            if working_stream:
                log.debug(f"Found working stream: {working_stream}")
                return working_stream

        log.debug(f"No working stream for {self}")

    async def get(self, index: int) -> Stream:
        streams = await self.streams
        if not 0 <= index < len(streams):
            raise StreamNotFound()

        return streams[index]

    @cached_property
    async def poster(self) -> Optional[str]:
        log.debug(f"{self} searching for poster")
        return await get_first([stream.poster for stream in await self.streams])

    def serialise_special(self, key: str, value: Any) -> BsonType:
        if key == "streams":
            # if there are no links/poster in a stream and it has already been "processed", get rid of it
            return [stream.state for stream in value if stream.persist or getattr(stream, "_links", True) or getattr(stream, "_poster", True)]
        elif key == "stream":
            return value.state

    @classmethod
    def deserialise_special(cls, key: str, value: BsonType) -> Any:
        from .. import streams

        if key == "streams":
            return list(filter(None, map(streams.load_stream, value)))
        elif key == "stream":
            return streams.load_stream(value)

    async def to_dict(self) -> Dict[str, BsonType]:
        raw_streams, stream, poster = await asyncio.gather(self.raw_streams, self.stream, self.poster)

        return {"embeds": raw_streams,
                "stream": await stream.to_dict() if stream else None,
                "poster": poster,
                "updated": self.last_update.isoformat()}
