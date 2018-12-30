import abc
import asyncio
import logging
import typing
from operator import attrgetter
from typing import Any, List, NamedTuple, Optional, Set

from prometheus_async.aio import time
from quart import request

from . import languages, sources
from .exceptions import AnimeNotFound, InvalidRequest, SourceNotFound, UIDUnknown
from .languages import Language
from .models import Anime, Episode, SearchResult, Stream, UID
from .telemetry import ANIME_QUERY_TYPE, ANIME_SEARCH_TIME, LANGUAGE_COUNTER, SOURCE_COUNTER
from .utils import alist, fuzzy_bool

log = logging.getLogger(__name__)

_DEFAULT = object()


class SearchFilter(NamedTuple):
    language: Language
    dubbed: bool

    def as_dict(self):
        return self._asdict()


class AnimeQuery(metaclass=abc.ABCMeta):
    class _Generic(metaclass=abc.ABCMeta):
        def __init__(self, **kwargs) -> None:
            cls = type(self)
            hints = typing.get_type_hints(cls)
            args = kwargs or request.args

            for key, typ in hints.items():
                value = args.get(key)
                if value is None:
                    if not hasattr(self, key):
                        raise KeyError(f"{self}: {key} missing!")
                    continue

                converter = getattr(cls, f"convert_{key}", typ)
                try:
                    value = converter(value)
                except (ValueError, TypeError):
                    raise ValueError(f"{self} couldn't convert {value} to {typ} for {key}")

                setattr(self, key, value)

        @classmethod
        def try_build(cls, **kwargs) -> Optional["AnimeQuery._Generic"]:
            try:
                return cls(**kwargs)
            except (ValueError, KeyError):
                return None

        def track_telemetry(self, language: Language, dubbed: bool, source: str):
            LANGUAGE_COUNTER.labels(language.value, "dub" if dubbed else "sub").inc()
            SOURCE_COUNTER.labels(source).inc()

            query_type = type(self).__name__
            ANIME_QUERY_TYPE.labels(query_type).inc()

        @abc.abstractmethod
        async def search_params(self) -> SearchFilter:
            ...

        @abc.abstractmethod
        async def resolve(self) -> Anime:
            ...

    class UID(_Generic):
        uid: UID

        async def search_params(self) -> SearchFilter:
            raise InvalidRequest("Can't search using a UID")

        async def resolve(self) -> Anime:
            if not self.uid:
                raise InvalidRequest("")

            anime = await sources.get_anime(self.uid)
            if not anime:
                raise UIDUnknown(self.uid)

            self.track_telemetry(self.uid.language, self.uid.dubbed, self.uid.source)
            return anime

    class Query(_Generic):
        anime: str

        language: Language = None
        convert_language = languages.get_lang

        dubbed: bool = None
        convert_dubbed = fuzzy_bool

        async def search_params(self) -> SearchFilter:
            return SearchFilter(self.language or Language.ENGLISH, bool(self.dubbed))

        async def resolve(self) -> Anime:
            filters = dict()

            if self.dubbed is not None:
                filters["dubbed"] = self.dubbed

            if self.language:
                filters["language"] = self.language.value

            anime = await sources.get_anime_by_title(self.anime, **filters)
            if not anime:
                raise AnimeNotFound(self.anime, dubbed=self.dubbed, language=self.language)

            self.track_telemetry(self.language, self.dubbed, type(anime).__name__)
            return anime

    @staticmethod
    def build(**kwargs) -> _Generic:
        for query_type in (AnimeQuery.UID, AnimeQuery.Query):
            query = query_type.try_build(**kwargs)
            if query:
                return query

        raise InvalidRequest("Please specify the anime using either its uid, "
                             "or a title (anime), language and dubbed value")


def _get_int_param(name: str, default: Any = _DEFAULT) -> int:
    try:
        value = request.args.get(name, type=int)
    except TypeError:
        value = None

    if value is None:
        if default is _DEFAULT:
            raise InvalidRequest(f"please specify {name}!")
        return default

    return value


@time(ANIME_SEARCH_TIME)
async def search_anime() -> List[SearchResult]:
    query = AnimeQuery.build()
    filters = await query.search_params()

    query = request.args.get("anime")
    if not query:
        raise InvalidRequest("No query specified")

    num_results = _get_int_param("results", 1)
    if not (0 < num_results <= 20):
        raise InvalidRequest(f"Can only request up to 20 results (not {num_results})")

    results_pool: Set[SearchResult] = set()

    try:
        anime = await alist(sources.get_animes_by_title(query, language=filters.language, dubbed=filters.dubbed))
    except Exception:
        log.exception("Couldn't search anime in database, moving on...")
    else:
        if anime:
            log.info(f"found {len(anime)}/{num_results} anime in database with matching query")
            results_pool.update(map(lambda a: SearchResult(a, 1), anime))

    if len(results_pool) < num_results:
        result_iter = sources.search_anime(query, language=filters.language, dubbed=filters.dubbed)
        consider_results = max(num_results, min(int(len(sources.SOURCES) * 1.5), 5))

        async for result in result_iter:
            if len(results_pool) >= consider_results:
                break

            results_pool.add(result)

    results = sorted(results_pool, key=attrgetter("certainty"), reverse=True)[:num_results]
    await asyncio.gather(*(result.anime.preload_attrs(*(set(Anime.ATTRS) - {"episodes"})) for result in results))

    return results[:num_results]


async def get_anime(**kwargs) -> Anime:
    return await AnimeQuery.build(**kwargs).resolve()


def get_episode_index() -> int:
    return _get_int_param("episode")


async def get_episode(episode_index: int = None, anime: Anime = None, **kwargs) -> Episode:
    if episode_index is None:
        episode_index = get_episode_index()

    anime = anime or await get_anime(**kwargs)
    return await anime.get(episode_index)


async def get_stream(stream_index: int = None, episode: Episode = None, **kwargs) -> Stream:
    if stream_index is None:
        stream_index = _get_int_param("stream")

    episode = episode or await get_episode(**kwargs)
    return await episode.get(stream_index)


async def get_source(source_index: int = None, episode: Episode = None, **kwargs) -> str:
    if source_index is None:
        source_index = _get_int_param("source")

    episode = episode or await get_episode(**kwargs)
    srcs = await episode.sources

    if not 0 <= source_index < len(srcs):
        raise SourceNotFound()

    return srcs[source_index]
