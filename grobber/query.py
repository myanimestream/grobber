import abc
import asyncio
import inspect
import logging
import typing
import uuid
from operator import attrgetter
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from quart import request

from . import languages, locals, sources
from .decorators import cached_property
from .exceptions import AnimeNotFound, InvalidRequest, UIDUnknown, UserNotFound
from .languages import Language
from .models import Anime, Episode, Stream, UID
from .utils import fuzzy_bool

log = logging.getLogger(__name__)

_DEFAULT = object()


class SearchFilter(NamedTuple):
    language: Language
    dubbed: bool

    def as_dict(self):
        return self._asdict()


class DBModelMeta(type):
    COLLECTION: str = None

    @property
    def collection(self) -> AsyncIOMotorCollection:
        if not self.COLLECTION:
            raise TypeError(f"Model {self} doesn't have a COLLECTION")

        return locals.db[self.COLLECTION]


class DBModel(metaclass=DBModelMeta):
    _id: ObjectId

    @classmethod
    def load(cls, document: Dict[str, Any]):
        inst = cls()
        hints = typing.get_type_hints(cls)

        for key, value in document.items():
            typ = hints.get(key)
            if not typ:
                continue

            if inspect.isfunction(typ) and hasattr(typ, "__supertype__"):
                typ = typ.__supertype__

            if isinstance(value, typ):
                value = value
            else:
                converter = getattr(cls, f"load_{key}", typ)
                value = converter(value)

            setattr(inst, key, value)

        return inst

    @classmethod
    async def find(cls, query, *, sort: List[Tuple[Union[str, List[str]], int]] = None):
        document = await cls.collection.find_one(query, sort=sort)
        if document:
            return cls.load(document)

        return None

    @classmethod
    async def find_all(cls, query):
        res: List[DBModel] = []

        async for document in cls.collection.find(query):
            res.append(cls.load(document))

        return res

    async def delete(self) -> None:
        await type(self).collection.delete_one(dict(_id=self._id))


class UserConfig(NamedTuple):
    language: Language
    dubbed: bool

    update_status: bool
    watch_percentage_tolerance: float
    replace_paid_streams: bool

    @property
    def query_params(self) -> SearchFilter:
        return SearchFilter(self.language, self.dubbed)


class User(DBModel):
    COLLECTION = "users"

    _id: ObjectId
    api_key: uuid.UUID

    config: UserConfig
    load_config = lambda doc: UserConfig(**doc)


class Query(DBModel):
    COLLECTION = "queries"

    _id: ObjectId
    user_id: ObjectId
    query: str
    uid: UID

    language: Language
    dubbed: bool

    @cached_property
    async def anime(self) -> Anime:
        return await sources.get_anime(self.uid)


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
            if anime:
                return anime
            else:
                raise UIDUnknown(self.uid)

    class UserQuery(_Generic):
        anime: str
        user: str

        async def get_user(self) -> User:
            user = await User.find(dict(api_key=self.user))
            if user is None:
                raise UserNotFound(self.user)
            return user

        async def search_params(self) -> SearchFilter:
            user = await self.get_user()
            return user.config.query_params

        async def resolve(self) -> Anime:
            user = await self.get_user()
            query = await Query.find(dict(query=self.anime, user={"$in": [user._id, None]}, **user.config.query_params.as_dict()),
                                     sort=[("user", -1)])
            if not query:
                raise AnimeNotFound(self.anime, user=user._id)

            return await query.anime

    class Query(_Generic):
        anime: str

        language: Language = None
        convert_language = languages.get_lang

        dubbed: bool = None
        convert_dubbed = fuzzy_bool

        async def search_params(self) -> SearchFilter:
            return SearchFilter(self.language or Language.ENGLISH, bool(self.dubbed))

        async def resolve(self) -> Anime:
            filters = dict(query=self.anime, user=None)

            if self.dubbed is not None:
                filters["dubbed"] = self.dubbed

            if self.language:
                filters["language"] = self.language.value

            query = await Query.find(filters)
            if not query:
                raise AnimeNotFound(self.anime, dubbed=self.dubbed, language=self.language)

            return await query.anime

    @staticmethod
    def build(**kwargs) -> _Generic:
        for query_type in (AnimeQuery.UID, AnimeQuery.UserQuery, AnimeQuery.Query):
            query = query_type.try_build(**kwargs)
            if query:
                return query

        raise InvalidRequest("Please specify the anime using either its uid, "
                             "a query (anime) and your api key (user), or a query, language and dubbed value")


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


async def search_anime() -> List[Anime]:
    query = AnimeQuery.build()
    filters = await query.search_params()

    args = request.args

    query = args.get("anime")
    if not query:
        raise InvalidRequest("No query specified")

    num_results = _get_int_param("results", 1)
    if not (0 < num_results <= 20):
        raise InvalidRequest(f"Can only request up to 20 results (not {num_results})")

    consider_results = max(num_results, 3)

    result_iter = sources.search_anime(query, language=filters.language, dubbed=filters.dubbed)

    results_pool = []
    async for result in result_iter:
        if len(results_pool) >= consider_results:
            break

        results_pool.append(result)

    results = sorted(results_pool, key=attrgetter("certainty"), reverse=True)[:num_results]
    await asyncio.gather(*(result.anime.preload_attrs() for result in results))

    return results[:num_results]


async def get_anime(**kwargs) -> Anime:
    return await AnimeQuery.build(**kwargs).resolve()


async def get_episode(episode_index: int = None, anime: Anime = None, **kwargs) -> Episode:
    if episode_index is None:
        episode_index = _get_int_param("episode")

    anime = anime or await get_anime(**kwargs)
    return await anime.get(episode_index)


async def get_stream(stream_index: int = None, episode: Episode = None, **kwargs) -> Stream:
    if stream_index is None:
        stream_index = _get_int_param("stream")

    episode = episode or await get_episode(**kwargs)
    return await episode.get(stream_index)
