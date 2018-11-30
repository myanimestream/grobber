import importlib
import logging
from operator import attrgetter
from typing import AsyncIterator, List, Type

from ..models import Stream
from ..request import Request

log = logging.getLogger(__name__)

_STREAMS = ["generic", "mp4upload", "rapidvideo", "vidstreaming"]
STREAMS: List[Type[Stream]] = []

_DENY_REGISTRATION = False


def register_stream(stream: Type[Stream]):
    global _DENY_REGISTRATION
    if _DENY_REGISTRATION:
        raise ImportError(f"{stream} is too late to register as a stream (Already sorted)")
    STREAMS.append(stream)


def _load_streams():
    global _DENY_REGISTRATION
    for SRC in _STREAMS:
        importlib.import_module("." + SRC, __name__)
    STREAMS.sort(key=attrgetter("PRIORITY"), reverse=True)
    _DENY_REGISTRATION = True


_load_streams()
log.info(f"Using Streams: {', '.join(stream.__name__ for stream in STREAMS)}")


async def get_stream(req: Request) -> AsyncIterator[Stream]:
    for stream in STREAMS:
        if await stream.can_handle(req):
            yield stream(req)
