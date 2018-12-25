# IGNORED due to ip restriction

import logging
import re
from typing import List, Match, Optional, Pattern

from . import register_stream
from ..decorators import cached_property
from ..models import Stream
from ..request import Request
from ..utils import add_http_scheme

log = logging.getLogger(__name__)

ENCODING_ALPHABET = "=/+9876543210zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA"
RE_EXTRACT_SOURCE = re.compile(r"src:d\('(.+?)',(\d+)\)", re.DOTALL)
RE_CLEAN_HREF: Pattern = re.compile(r"[^A-Za-z0-9+/=]")


def decode_url(encoded: str, code: int) -> str:
    encoded = RE_CLEAN_HREF.sub("", encoded)
    decoded = ""
    sm: List[int] = [None] * 4
    i = 0
    str_len = len(encoded)
    while i < str_len:
        for j in range(4):
            sm[j % 4] = ENCODING_ALPHABET.index(encoded[i])
            i += 1
        char_code = ((sm[0] << 0x2) | (sm[1] >> 0x4)) ^ code
        decoded += chr(char_code)
        if sm[2] != 0x40:
            char_code = ((sm[1] & 0xf) << 0x4) | (sm[2] >> 0x2)
            decoded += chr(char_code)
        if sm[3] != 0x40:
            char_code = ((sm[2] & 0x3) << 0x6) | sm[3]
            decoded += chr(char_code)
    return decoded


def extract_stream(text: str) -> Optional[str]:
    match: Match = RE_EXTRACT_SOURCE.search(text)
    if match:
        encoded_href, code = match.groups()
        log.debug(f"decoding url {encoded_href} with code {code}")
        href = decode_url(encoded_href, int(code))
        log.debug(f"Got {href}")
        return href
    else:
        log.info("Couldn't extract source from page")


class Streamango(Stream):
    HOST = "streamango.com"

    @cached_property
    async def poster(self) -> Optional[str]:
        video = (await self._req.bs).find("video", id="mgvideo")
        if video:
            link = video.attrs.get("poster")
            if link and await Request(link).head_success:
                return link

    @cached_property
    async def links(self) -> List[str]:
        source = extract_stream(await self._req.text)
        if source:
            link = Request(add_http_scheme(source))
            if await link.head_success:
                return [await link.url]
        return []

    @cached_property
    async def external(self) -> bool:
        return False


register_stream(Streamango)
