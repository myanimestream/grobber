import abc
import asyncio
import logging
import typing
from operator import attrgetter
from typing import Any, List, NamedTuple, Optional, Set

from prometheus_async.aio import time
from quart import request

from . import languages
from .anime import Anime, AnimeNotFound, Episode, SearchResult, SourceNotFound, Stream, sources
from .exceptions import InvalidRequest, UIDUnknown
from .languages import Language
from .search_results import find_cached_searches, get_cached_searches, store_cached_search
from .telemetry import ANIME_QUERY_TYPE, ANIME_RESOLVE_TIME, ANIME_SEARCH_TIME, LANGUAGE_COUNTER, SOURCE_COUNTER
from .uid import MediaType, UID
from .utils import alist, fuzzy_bool, get_certainty

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

            query_type = type(self).__qualname__
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

            self.track_telemetry(self.language, self.dubbed, type(anime).__qualname__)
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

    exact_search_results = await get_cached_searches(MediaType.ANIME, query, num_results)
    if exact_search_results:
        log.info("Found exact search result")
        exact_anime_results: List[Anime] = await asyncio.gather(*(sources.build_anime_from_doc(sr["_id"], sr) for sr in exact_search_results))
        return [SearchResult(anime, get_certainty(await anime.title, query)) for anime in exact_anime_results]

    results_pool: Set[SearchResult] = set()

    # first try to find animes matching the query in the database
    try:
        anime = await alist(sources.get_animes_by_title(query, language=filters.language, dubbed=filters.dubbed))
    except Exception:
        log.exception("Couldn't search anime in database, moving on...")
    else:
        if anime:
            log.info(f"found {len(anime)}/{num_results} anime in database with matching title")
            results_pool.update(map(lambda a: SearchResult(a, 1), anime))

    cached_search_results = await find_cached_searches(MediaType.ANIME, query, max_results=num_results)
    anime_search_results: List[Anime] = await asyncio.gather(*(sources.build_anime_from_doc(sr["_id"], sr) for sr in cached_search_results))
    cached_added = 0
    for search_result in anime_search_results:
        certainty = get_certainty(await search_result.title, query)
        if certainty >= .5:
            results_pool.add(SearchResult(search_result, certainty))
            cached_added += 1

    log.info(f"found {cached_added}/{num_results} in cached search results ({len(anime_search_results) - cached_added} discarded)")

    log.debug(f"current total: {len(results_pool)}/{num_results}")

    # if we didn't get enough use the actual search
    if len(results_pool) < num_results:
        # look at a sensible amount of search results (at least 1.5 times the amount of sources up to 5 and then just use the requested amount)
        consider_results = max(num_results, min(int(len(sources.SOURCES) * 1.5), 5))

        # use a separate pool for this so we can manipulate them later
        search_results: Set[SearchResult] = set()

        result_iter = sources.search_anime(query, language=filters.language, dubbed=filters.dubbed)
        async for result in result_iter:
            if result not in search_results and result not in results_pool:
                search_results.add(result)
            else:
                log.debug(f"ignoring {result} because it's already in the pool")

            if len(results_pool) + len(search_results) >= consider_results:
                break

        # preload all uids
        uids: List[UID] = await asyncio.gather(*(res.anime.uid for res in search_results))
        stored_animes = await sources.get_animes(uids)

        # try to find these results in the database and if they exist, use them instead of the newly created ones
        for res in search_results:
            uid = await res.anime.uid
            stored_anime = stored_animes.get(uid)
            if stored_anime:
                log.debug(f"found {res} in database")
                res.anime = stored_anime

        results_pool.update(search_results)

        # cache the search results for this search
        uids = await asyncio.gather(*(result.anime.uid for result in results_pool))
        await store_cached_search(MediaType.ANIME, query, num_results, uids)
        log.info(f"cached {len(uids)} search results for \"{query}\"")

    log.info(f"found {len(results_pool)}/{num_results}")
    results = sorted(results_pool, key=attrgetter("certainty"), reverse=True)[:num_results]
    await asyncio.gather(*(result.anime.preload_attrs(*Anime.PRELOAD_ATTRS) for result in results))

    # sort by certainty, title, episode count
    results.sort(key=lambda sr: (sr.certainty, getattr(sr.anime, "_title", ""), getattr(sr.anime, "_episode_count", 0)), reverse=True)

    return results


@time(ANIME_RESOLVE_TIME)
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
