import logging
import re
from collections import namedtuple
from typing import List, Match, Optional, Pattern

from . import register_stream
from ..decorators import cached_property
from ..models import Stream
from ..request import Request
from ..stateful import Expiring

log = logging.getLogger(__name__)

RE_EXTRACT_CODE: Pattern = re.compile(
    r"<div id=\"player\"><script type='text/javascript'>eval\(function\(p,a,c,k,e,d\){.+?}\('(.+?)',(\d+),\d+,'([\w|]+)'", re.DOTALL
)
RE_EXTRACT_DATA: Pattern = re.compile(r"\"file\":\s*\"(.+?)\",\s*\"image\":\s*\"(.+?)\",", re.DOTALL)


def base_n(num, b, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
    return ((num == 0) and numerals[0]) or (base_n(num // b, b, numerals).lstrip(numerals[0]) + numerals[num % b])


def decode(code: str, radix: int, encoding_map: List[str]) -> str:
    for i in range(len(encoding_map) - 1, -1, -1):
        if encoding_map[i]:
            code = re.sub(r"\b" + base_n(i, radix) + r"\b", encoding_map[i], code)
    return code


PlayerData = namedtuple("PlayerData", ("video", "poster"))


def extract_player_data(text: str) -> Optional[PlayerData]:
    match: Match = RE_EXTRACT_CODE.search(text)
    if match:
        code, radix, encoding_map = match.groups()
        text = decode(code, int(radix), encoding_map.split("|"))
        match: Match = RE_EXTRACT_DATA.search(text)
        if match:
            return PlayerData(*match.groups())
        else:
            log.debug("Mp4Upload Couldn't extract file and image from decrypted code")
    else:
        log.debug("Mp4Upload Couldn't extract encrypted code from page")

    return None


class Mp4Upload(Stream):
    ATTRS = ("player_data",)
    EXPIRE_TIME = Expiring.HOUR

    HOST = "mp4upload.com"

    @cached_property
    def player_data(self) -> PlayerData:
        player_data = extract_player_data(self._req.text)
        if player_data:
            return player_data
        else:
            log.debug("Mp4Upload unable to extract player data")
            return PlayerData(None, None)

    @cached_property
    def poster(self) -> Optional[str]:
        link = self.player_data[1]
        if link and Request(link).head_success:
            return link

    @cached_property
    def links(self) -> List[str]:
        source = self.player_data[0]
        if source and Request(source).head_success:
            return [source]
        return []


register_stream(Mp4Upload)
