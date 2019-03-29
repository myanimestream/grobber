import logging
import re
from enum import Enum
from typing import Optional

from quart.routing import BaseConverter

from .exceptions import UIDInvalid
from .languages import Language, get_lang

log = logging.getLogger(__name__)

# source-anime_id-language(_dub)?
RE_LEGACY_UID_PARSER = re.compile(r"^(.+)-(.+)-(.+?)(_dub)?$")
# medium_type-medium_id(-source)?-language(_dub)?
RE_UID_PARSER = re.compile(r"^([^-]+)-([^-]+)(?:-([^-]+))?-([^-]+?)(_dub)?$")


class MediumType(Enum):
    ANIME = "a"
    MANGA = "m"


class UID(str, BaseConverter):
    __parsed__: bool

    _medium_type: MediumType
    _medium_id: str
    _source: Optional[str]
    _language: Language
    _dubbed: bool

    @property
    def medium_type(self) -> MediumType:
        self.parse()
        return self._medium_type

    @property
    def medium_id(self) -> str:
        self.parse()
        return self._medium_id

    @property
    def source(self) -> Optional[str]:
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
    def create(cls, media_type: MediumType, media_id: str, source: Optional[str], language: Language, dubbed: bool) -> "UID":
        dubbed_str = "_dub" if dubbed else ""
        source_str = f"-{source}" if source else ""
        uid = UID(f"{media_type.value}-{media_id}{source_str}-{language.value}{dubbed_str}")

        uid._medium_type = media_type
        uid._medium_id = media_id
        uid._source = source
        uid._language = language
        uid._dubbed = dubbed

        uid.__parsed__ = True

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
        try:
            parsed = self.__parsed__
            if parsed:
                return
        except AttributeError:
            pass

        match = RE_UID_PARSER.match(self)
        if match:
            self._medium_type = MediumType(match.group(1))
            self._medium_id, self._source = match.group(2, 3)
            self._language = get_lang(match.group(4))
            self._dubbed = bool(match.group(5))
        else:
            log.debug(f"invalid uid {self}, trying legacy")
            match = RE_LEGACY_UID_PARSER.match(self)
            if not match:
                raise UIDInvalid(self)

            self._medium_type = MediumType.ANIME
            self._source, self._medium_id = match.group(1, 2)
            self._language = get_lang(match.group(3))
            self._dubbed = bool(match.group(4))

        self.__parsed__ = True
