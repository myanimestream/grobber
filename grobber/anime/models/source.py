__all__ = ["Source"]

from typing import NamedTuple


class Source(NamedTuple):
    mime_type: str
    src: str
