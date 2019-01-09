import logging
import re
from enum import Enum

from quart.routing import BaseConverter

from .exceptions import UIDInvalid
from .languages import Language, get_lang

log = logging.getLogger(__name__)

# source-anime_id-language(_dub)?
RE_LEGACY_UID_PARSER = re.compile(r"^(.+)-(.+)-(.+?)(_dub)?$")
# media_type-media_id-source-language(_dub)?
RE_UID_PARSER = re.compile(r"^(.+)-(.+)-(.+)-(.+?)(_dub)?$")


class MediaType(Enum):
    ANIME = "a"
    MANGA = "m"


class UID(str, BaseConverter):
    _parsed: bool

    _media_type: MediaType
    _media_id: str
    _source: str
    _language: Language
    _dubbed: bool

    @property
    def media_type(self) -> MediaType:
        self.parse()
        return self._media_type

    @property
    def media_id(self) -> str:
        self.parse()
        return self._media_id

    @property
    def source(self) -> str:
        self.parse()
        return self._source

    @property
    def language(self) -> Language:
        self.parse()
        return self._language

    @property
    def dubbed(self) -> bool:
        self.parse()
        return self._dubbed

    @classmethod
    def create(cls, media_type: MediaType, media_id: str, source: str, language: Language, dubbed: bool) -> "UID":
        dubbed_str = "_dub" if dubbed else ""
        uid = UID(f"{media_type.value}-{media_id}-{source}-{language.value}{dubbed_str}")

        uid._media_type = media_type
        uid._media_id = media_id
        uid._source = source
        uid._language = language
        uid._dubbed = dubbed

        uid._parsed = True

        return uid

    @classmethod
    def create_media_id(cls, name: str) -> str:
        name = name.strip().lower() \
            .replace(" ", "")

        return "".join((c if c.isalnum() else f"_{ord(c):x}_") for c in name)

    def to_python(self, value: str) -> "UID":
        return UID(value)

    def to_url(self, value: "UID") -> str:
        return super().to_url(value)

    def parse(self) -> None:
        if getattr(self, "_parsed", False):
            return

        match = RE_UID_PARSER.match(self)
        if match:
            self._media_type = MediaType(match.group(1))
            self._media_id, self._source = match.group(2, 3)
            self._language = get_lang(match.group(4))
            self._dubbed = bool(match.group(5))
        else:
            log.debug(f"invalid uid {self}, trying legacy")
            match = RE_LEGACY_UID_PARSER.match(self)
            if not match:
                raise UIDInvalid(self)

            self._media_type = MediaType.ANIME
            self._source, self._media_id = match.group(1, 2)
            self._language = get_lang(match.group(3))
            self._dubbed = bool(match.group(4))

        self._parsed = True
