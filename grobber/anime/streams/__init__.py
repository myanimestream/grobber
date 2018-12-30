import importlib
import logging
from operator import attrgetter
from typing import Any, AsyncIterator, Dict, List, Optional, Type

from grobber.request import Request
from ..models import Stream

log = logging.getLogger(__name__)

_STREAMS = ["generic", "mp4upload", "openload", "rapidvideo", "streamango", "vidstreaming"]
STREAMS: List[Type[Stream]] = []
STREAM_MAP: Dict[str, Type[Stream]] = {}

_DENY_REGISTRATION = False


def register_stream(stream: Type[Stream]):
    global _DENY_REGISTRATION
    if _DENY_REGISTRATION:
        raise ImportError(f"{stream} is too late to register as a stream (Already sorted)")
    STREAMS.append(stream)
    STREAM_MAP[stream.__qualname__] = stream


def load_stream(data: Dict[str, Any]) -> Optional[Stream]:
    name: str = data.get("cls")
    if name:
        # previous versions would use fully qualified names. rsplit for backward-compatibility
        *_, name = name.rsplit(".", 1)
        cls = STREAM_MAP.get(name)
        if cls:
            return cls.from_state(data)

    return None


def _load_streams():
    global _DENY_REGISTRATION
    for SRC in _STREAMS:
        importlib.import_module("." + SRC, __name__)
    STREAMS.sort(key=attrgetter("PRIORITY"), reverse=True)
    _DENY_REGISTRATION = True


_load_streams()
log.info(f"Using Streams: {', '.join(stream.__qualname__ for stream in STREAMS)}")


async def get_stream(req: Request) -> AsyncIterator[Stream]:
    for stream in STREAMS:
        if await stream.can_handle(req):
            yield stream(req)
