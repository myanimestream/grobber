import importlib
import logging
from operator import attrgetter
from typing import Iterator, List, Type

from ..models import Stream
from ..request import Request

log = logging.getLogger(__name__)

_STREAMS = ["mp4upload", "vidstreaming", "generic"]
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
log.info(f"Using Streams: {[stream.__name__ for stream in STREAMS]}")


def get_stream(req: Request) -> Iterator[Stream]:
    for stream in STREAMS:
        if stream.can_handle(req):
            yield stream(req)
