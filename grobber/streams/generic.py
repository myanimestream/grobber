import logging
import re
from typing import List, Optional, Pattern

from . import register_stream
from ..decorators import cached_property
from ..models import Stream
from ..request import Request
from ..utils import add_http_scheme

log = logging.getLogger(__name__)

RE_URL_MATCHER = r"\b((http(s)?:)?(//)?[/\w.\-]+\.(" + "{suffix}" + r"))\b"

RE_VIDEO_LINK_MATCHER = re.compile(RE_URL_MATCHER.format(suffix="mp4|webm|ogg"), re.DOTALL)
RE_IMAGE_LINK_MATCHER = re.compile(RE_URL_MATCHER.format(suffix="jpg|gif|png"), re.DOTALL)

BLOCKED_HOSTS = ["estream.xyz", "estream.to"]


class Generic(Stream):
    PRIORITY = 0

    @classmethod
    def can_handle(cls, req: Request) -> bool:
        if req.yarl.host in BLOCKED_HOSTS:
            log.debug(f"ignoring {req} because it's blocked")
            return False
        return True

    def get_links(self, pattern: Pattern) -> List[Request]:
        if not self._req.success:
            log.warning(f"couldn't access {self}")
            return []
        links = set()
        for group in pattern.findall(self._req.text):
            url = add_http_scheme(group[0], self._req.url)
            links.add(Request(url))
        return list(links)

    @cached_property
    def poster(self) -> Optional[str]:
        potential_links = self.get_links(RE_IMAGE_LINK_MATCHER)
        poster = next((poster.url for poster in potential_links if poster.head_success), None)
        if poster:
            log.debug(f"Found poster for {self}: {poster}")
        return poster

    @cached_property
    def links(self) -> List[str]:
        potential_links = self.get_links(RE_VIDEO_LINK_MATCHER)
        return Stream.get_successful_links(potential_links)


register_stream(Generic)
