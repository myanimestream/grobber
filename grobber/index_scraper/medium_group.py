from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from grobber.anime import SourceAnime
from grobber.anime.group import AnimeGroup
from grobber.uid import MediumType, UID
from .medium import Medium, MediumData, medium_from_document, source_anime_from_medium

__all__ = ["MediumGroup",
           "medium_group_from_document",
           "source_animes_from_medium_group",
           "source_group_from_medium_group"]

INCOMPATIBLE_MEDIUM_ERROR = "Provided media is not compatible! {medium} does not share {key} with others: {media}"


class MediumGroup(MediumData):
    uid: UID
    medium_type: str
    medium_id: str
    language: str
    dubbed: bool

    title: str
    aliases: List[str]
    thumbnails: List[str]
    episode_count: Optional[int]

    def __init__(self, media: Iterable[MediumData]) -> None:
        self._media = list(media)

        media_iter = iter(self._media)
        try:
            medium = next(media_iter)
        except StopIteration:
            raise ValueError("Media must not be empty")

        self.medium_type = medium.medium_type
        self.medium_id = medium.medium_id
        self.language = medium.language
        self.dubbed = medium.dubbed

        self.uid = UID.create(self.medium_type_enum, self.medium_id, None, self.language_enum, self.dubbed)

        self.title = medium.title

        aliases: Set[str] = set(medium.aliases)
        thumbnails: Set[Optional[str]] = {medium.thumbnail}
        episode_counts: Set[Optional[int]] = {medium.episode_count}

        for medium in media_iter:
            if medium.medium_type != self.medium_type:
                raise ValueError(INCOMPATIBLE_MEDIUM_ERROR.format(media=self._media, medium=medium, key="medium type"))

            if medium.medium_id != self.medium_id:
                raise ValueError(INCOMPATIBLE_MEDIUM_ERROR.format(media=self._media, medium=medium, key="medium id"))

            if medium.language != self.language:
                raise ValueError(INCOMPATIBLE_MEDIUM_ERROR.format(media=self._media, medium=medium, key="language"))

            if medium.dubbed != self.dubbed:
                raise ValueError(INCOMPATIBLE_MEDIUM_ERROR.format(media=self._media, medium=medium, key="dubbed"))

            aliases.update(medium.aliases)
            thumbnails.add(medium.thumbnail)
            episode_counts.add(medium.episode_count)

        self.aliases = list(aliases)
        self.thumbnails = list(filter(None, thumbnails))

        try:
            episode_count = max(filter(None, episode_counts))
        except ValueError:
            episode_count = None

        self.episode_count = episode_count

    def __len__(self) -> int:
        return len(self._media)

    def __repr__(self) -> str:
        cls_name = type(self).__name__
        return f"{cls_name}({repr(self._media)})"

    def __iter__(self) -> Iterator[MediumData]:
        return iter(self._media)

    @property
    def media(self) -> List[MediumData]:
        return self._media

    @property
    def thumbnail(self) -> Optional[str]:
        try:
            return self.thumbnails[0]
        except IndexError:
            return None


def medium_group_from_document(documents: List[Dict[str, Any]]) -> MediumGroup:
    media = map(medium_from_document, documents)
    return MediumGroup(media)


def _get_source_anime_info_from_medium_group(medium_group: MediumGroup) -> List[Tuple[UID, SourceAnime]]:
    animes: List[Tuple[UID, SourceAnime]] = []
    for medium in medium_group:
        if isinstance(medium, Medium):
            animes.append((medium.uid, source_anime_from_medium(medium)))
        elif isinstance(medium, MediumGroup):
            animes.extend(_get_source_anime_info_from_medium_group(medium))

    return animes


def source_animes_from_medium_group(medium_group: MediumGroup) -> List[SourceAnime]:
    return [anime for uid, anime in _get_source_anime_info_from_medium_group(medium_group)]


def source_group_from_medium_group(medium_group: MediumGroup) -> Optional[AnimeGroup]:
    if medium_group.medium_type_enum == MediumType.ANIME:
        uids, animes = zip(*_get_source_anime_info_from_medium_group(medium_group))
        return AnimeGroup(uids, medium_group.title, medium_group.language_enum, medium_group.dubbed, animes=animes)
