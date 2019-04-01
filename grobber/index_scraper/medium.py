import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from grobber.anime import SourceAnime
from grobber.languages import Language, get_lang
from grobber.request import Request
from grobber.uid import MediumType, UID

__all__ = ["Medium",
           "create_medium",
           "medium_to_document",
           "medium_from_document",
           "medium_from_source_anime_document", "source_anime_from_medium"]


@dataclass(frozen=True)
class Medium:
    _id: str
    source_cls: str
    updated: datetime = dataclasses.field(compare=False)
    medium_type: str

    language: str
    dubbed: bool

    title: str
    aliases: List[str] = dataclasses.field(compare=False)
    href: str

    thumbnail: Optional[str] = None
    episode_count: Optional[int] = None

    @property
    def raw_uid(self) -> str:
        return self._id

    @property
    def uid(self) -> UID:
        return UID(self._id)

    @property
    def medium_type_enum(self) -> MediumType:
        return MediumType(self.medium_type)

    @property
    def language_enum(self) -> Language:
        return get_lang(self.language)


def create_medium(source_cls: str, medium_type: MediumType, title: str, href: str, *,
                  language: Language,
                  dubbed: bool,
                  uid: str = None,
                  updated: datetime = None,
                  episode_count: int = None,
                  thumbnail: str = None,
                  aliases: List[str] = None) -> Medium:
    if uid is None:
        uid = UID.create(medium_type, UID.create_media_id(title), source_cls, language, dubbed)
    else:
        uid = str(uid)

    if aliases is None:
        aliases = []

    if updated is None:
        updated = datetime.utcnow()

    return Medium(_id=uid,
                  source_cls=source_cls,
                  updated=updated,
                  medium_type=medium_type.value,
                  language=language.value,
                  dubbed=dubbed,
                  title=title,
                  aliases=aliases,
                  episode_count=episode_count,
                  href=href,
                  thumbnail=thumbnail)


def medium_to_document(medium: Medium) -> Dict[str, Any]:
    return dataclasses.asdict(medium)


MEDIUM_FIELDS: Tuple[dataclasses.Field] = dataclasses.fields(Medium)
MEDIUM_FIELD_NAMES: Set[str] = {field.name for field in MEDIUM_FIELDS}


def medium_from_document(doc: Dict[str, Any]) -> Medium:
    return Medium(**doc)


def medium_from_source_anime_document(doc: Dict[str, Any]) -> Medium:
    from grobber.stateful import Stateful
    special_marker: str = getattr(Stateful, "_SPECIAL_MARKER")

    medium_doc = {key: value for key, value in doc if key in MEDIUM_FIELD_NAMES}

    medium_doc.setdefault("updated", doc["last_update"])
    medium_doc.setdefault("medium_type", MediumType.ANIME.value)

    medium_doc.setdefault("dubbed", doc["is_dub"])
    medium_doc.setdefault("language", doc[f"language{special_marker}"])

    medium_doc.setdefault("aliases", [])
    medium_doc.setdefault("href", doc["req"]["url"])

    return medium_from_document(medium_doc)


def source_anime_from_medium(medium: Medium) -> SourceAnime:
    from grobber.anime import sources
    cls = sources.get_source(medium.source_cls)

    req = Request(medium.href)
    return cls(req, data=dict(
        is_dub=medium.dubbed,
        language=medium.language_enum,
        title=medium.title,
        thumbnail=medium.thumbnail,
        episode_count=medium.episode_count,
    ))
