import abc
import asyncio
import logging
from contextlib import suppress
from operator import attrgetter
from typing import Any, Callable, List, NamedTuple, Set, Tuple, TypeVar, Union, cast, get_type_hints

from quart import Request, request

from . import index_scraper, languages
from .anime import Anime, AnimeNotFound, Episode, SearchResult, SourceAnime, SourceNotFound, Stream, sources
from .anime.group import AnimeGroup, get_anime_group, get_anime_group_by_title, group_animes
from .exceptions import InvalidRequest, UIDUnknown
from .languages import Language
from .locals import source_index_collection
from .uid import MediumType, UID
from .utils import alist, fuzzy_bool, get_certainty

request = cast(Request, request)

log = logging.getLogger(__name__)

T = TypeVar("T")
U = TypeVar("U")
_DEFAULT = object()


def _get_arg(*names: str, cls: Callable[[str], T] = None, default: U = _DEFAULT) -> Union[T, U]:
    rep_name: str = names[0]

    for name in names:
        try:
            value = request.args[name]
        except KeyError:
            continue

        if cls is None:
            return value

        try:
            return cls(value)
        except Exception:
            continue

    if default is _DEFAULT:
        raise InvalidRequest(f"No valid value for parameter \"{rep_name}\" set!")
    else:
        return default


def get_lookup_spec() -> Tuple[Language, bool, bool]:
    language = _get_arg("language", cls=languages.get_lang, default=Language.ENGLISH)
    dubbed = _get_arg("dubbed", cls=fuzzy_bool, default=False)
    group = _get_arg("group", cls=fuzzy_bool, default=True)
    return language, dubbed, group


class SearchFilter(NamedTuple):
    language: Language
    dubbed: bool

    def as_dict(self):
        return self._asdict()


class Query(metaclass=abc.ABCMeta):
    def __init__(self, **kwargs) -> None:
        cls = type(self)
        hints = get_type_hints(cls)
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

    def __repr__(self) -> str:
        attrs: List[str] = []

        for key, value in vars(self).items():
            if key.startswith("_") or key.endswith("_"):
                continue
            else:
                attrs.append(f"{key}: {value}")

        attrs_str = ", ".join(attrs)
        return f"{type(self).__name__} ({attrs_str})"

    @classmethod
    def try_build(cls, **kwargs):
        try:
            return cls(**kwargs)
        except (ValueError, KeyError):
            return None

    @abc.abstractmethod
    async def resolve(self) -> Any:
        ...


class AnimeQuery(Query):
    @abc.abstractmethod
    async def search_params(self) -> SearchFilter:
        ...

    @staticmethod
    def build(**kwargs) -> "AnimeQuery":
        for query_type in (UIDAnimeQuery, QueryAnimeQuery):
            query = query_type.try_build(**kwargs)
            if query:
                return cast(AnimeQuery, query)

        raise InvalidRequest("Please specify the anime using either its uid, "
                             "or a title (anime), language and dubbed value")


class UIDAnimeQuery(AnimeQuery):
    uid: UID

    async def search_params(self) -> SearchFilter:
        raise InvalidRequest("Can't search using a UID")

    async def resolve(self) -> SourceAnime:
        if not self.uid:
            raise InvalidRequest("Missing uid parameter")

        if self.uid.source is None:
            anime = await get_anime_group(self.uid)
        else:
            anime = await sources.get_anime(self.uid)
            if not anime:
                log.info(f"{self} uid not found in anime collection, trying source index!")
                medium = await index_scraper.get_medium(source_index_collection, self.uid)
                if medium is not None:
                    anime = index_scraper.source_anime_from_medium(medium)

        if not anime:
            raise UIDUnknown(self.uid)

        return anime


class QueryAnimeQuery(AnimeQuery):
    anime: str

    language: Language = None
    convert_language = languages.get_lang

    dubbed: bool = None
    convert_dubbed = fuzzy_bool

    group: bool = True
    convert_group = fuzzy_bool

    async def search_params(self) -> SearchFilter:
        return SearchFilter(self.language or Language.ENGLISH, bool(self.dubbed))

    async def resolve(self) -> SourceAnime:
        filters = dict()

        if self.dubbed is not None:
            filters["dubbed"] = self.dubbed

        if self.language:
            filters["language"] = self.language

        if self.group:
            anime = await get_anime_group_by_title(self.anime, **filters)
        else:
            anime = await sources.get_anime_by_title(self.anime, **filters)

        if not anime:
            raise AnimeNotFound(self.anime, dubbed=self.dubbed, language=self.language)

        return anime


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


async def _search_anime(query: str, filters: SearchFilter, num_results: int) -> Set[SearchResult]:
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

    log.debug(f"current total: {len(results_pool)}/{num_results}")

    media = cast(List[index_scraper.Medium],
                 await index_scraper.get_media_by_title(
                     source_index_collection, MediumType.ANIME, query,
                     language=filters.language,
                     dubbed=filters.dubbed,
                     group=False
                 ))

    for medium in media:
        try:
            anime = index_scraper.source_anime_from_medium(medium)
        except Exception:
            log.exception(f"Couldn't convert medium to anime ({medium}), moving on...")
        else:
            log.debug(f"adding {anime} from medium {medium} to pool")
            results_pool.add(SearchResult(anime, 1))

    log.debug(f"current total: {len(results_pool)}/{num_results}")

    # if we didn't get enough, use the actual search
    if len(results_pool) < num_results:
        # look at a sensible amount of search results (at least 1.5 times the amount of sources up
        # to 5 and then just use the requested amount)
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

    return results_pool


def search_result_score(result: SearchResult) -> Any:
    anime = result.anime

    title = str(getattr(anime, "_title", ""))
    episode_count = int(getattr(anime, "_episode_count", 0))

    if isinstance(anime, AnimeGroup):
        source_count = anime.source_count
    else:
        source_count = 1

    return result.certainty, title, episode_count, source_count


async def search_anime() -> List[SearchResult]:
    query = AnimeQuery.build()
    filters = await query.search_params()

    query = request.args.get("anime")
    if not query:
        raise InvalidRequest("No query specified")

    num_results = _get_int_param("results", 1)
    if not (0 < num_results <= 20):
        raise InvalidRequest(f"Can only request up to 20 results (not {num_results})")

    group: bool = fuzzy_bool(request.args.get("group"), default=True)
    results_pool = await _search_anime(query, filters, num_results)

    if group:
        groups = await group_animes(result.anime for result in results_pool)
        results_pool = {SearchResult(g, get_certainty(await g.title, query)) for g in groups}

    log.info(f"found {len(results_pool)}/{num_results}")
    results = sorted(results_pool, key=attrgetter("certainty"), reverse=True)[:num_results]

    with suppress(AttributeError):
        await asyncio.gather(*(result.anime.preload_attrs(*SourceAnime.PRELOAD_ATTRS) for result in results))

    # sort by certainty, title, episode count
    results.sort(key=search_result_score, reverse=True)

    return results


async def get_anime(**kwargs) -> SourceAnime:
    return await AnimeQuery.build(**kwargs).resolve()


def get_episode_index(**kwargs) -> int:
    return _get_int_param("episode", **kwargs)


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
