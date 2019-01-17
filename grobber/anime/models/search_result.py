__all__ = ["SearchResult"]

import logging
from typing import Any, Dict, NamedTuple

from .anime import Anime

log = logging.getLogger(__name__)


class SearchResult(NamedTuple):
    anime: Anime
    certainty: float

    def __str__(self) -> str:
        return f"<{round(100 * self.certainty)}% {self.anime}>"

    def __hash__(self) -> int:
        return hash(self.anime)

    async def to_dict(self) -> Dict[str, Any]:
        return {"anime": await self.anime.to_dict(),
                "certainty": self.certainty}
