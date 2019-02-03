__all__ = ["Source"]

from dataclasses import dataclass


@dataclass
class Source:
    mime_type: str
    src: str
