import logging
import re
from typing import List, Optional

from . import register_stream
from ..decorators import cached_property
from ..models import Stream
from ..request import Request
from ..utils import parse_js_json

log = logging.getLogger(__name__)

RE_EXTRACT_SETUP = re.compile(r"playerInstance\.setup\((.+?)\);", re.DOTALL)


def extract_player_data(text: str) -> dict:
    match = RE_EXTRACT_SETUP.search(text)
    if not match:
        log.debug("Couldn't find player data")
        return {}
    return parse_js_json(match.group(1))


class Vidstreaming(Stream):
    ATTRS = ("player_data",)

    HOST = "vidstreaming.io"

    @cached_property
    def player_data(self) -> dict:
        return extract_player_data(self._req.text)

    @cached_property
    def poster(self) -> Optional[str]:
        link = self.player_data.get("image")
        if link and Request(link).head_success:
            return link
        return None

    @cached_property
    def links(self) -> List[str]:
        raw_sources = self.player_data.get("sources")
        if not raw_sources:
            return []
        sources = [Request(source["file"]) for source in raw_sources]
        log.debug(f"found sources {sources}")
        return self.get_successful_links(sources)


register_stream(Vidstreaming)
