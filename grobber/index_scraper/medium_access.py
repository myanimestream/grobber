import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, Generic, List, Optional, TypeVar, overload

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorCommandCursor
from pymongo import DESCENDING

from grobber.languages import Language
from grobber.uid import MediumType, UID
from grobber.utils import AIterable, aiter, alist
from .medium import Medium, MediumData, medium_from_document
from .medium_group import MediumGroup, medium_group_from_document

__all__ = ["get_medium", "get_medium_group", "get_medium_group_by_uid", "get_medium_data",
           "SearchItem",
           "map_load_media",
           "search_media",
           "get_media_by_title"]

log = logging.getLogger(__name__)

T = TypeVar("T")


async def get_medium(collection: AsyncIOMotorCollection, uid: str) -> Optional[Medium]:
    doc = await collection.find_one(uid)
    if doc is None:
        return None
    else:
        return medium_from_document(doc)


async def get_medium_group(collection: AsyncIOMotorCollection,
                           medium_type: MediumType, medium_id: str,
                           language: Language,
                           dubbed: bool) -> Optional[MediumGroup]:
    cursor = collection.find({
        "medium_type": medium_type.value,
        "medium_id": medium_id,
        "language": language.value,
        "dubbed": dubbed,
    })

    documents = await cursor.to_list(None)
    if not documents:
        return None

    return medium_group_from_document(documents)


async def get_medium_group_by_uid(collection: AsyncIOMotorCollection, uid: UID) -> Optional[MediumGroup]:
    return await get_medium_group(collection, uid.medium_type, uid.medium_id, uid.language, uid.dubbed)


async def get_medium_data(collection: AsyncIOMotorCollection, uid: UID) -> Optional[MediumData]:
    if uid.source is None:
        return await get_medium_group_by_uid(collection, uid)
    else:
        return await get_medium(collection, uid)


@dataclass(frozen=True)
class SearchItem(Generic[T]):
    item: T
    score: float


def _pipeline_limit_and_skip(limit: int = None, skip: int = None) -> list:
    pipeline = []

    if limit is not None:
        if skip is None:
            absolute_limit = limit
        else:
            absolute_limit = limit + skip

        pipeline.append({"$limit": absolute_limit})

    if skip is not None:
        pipeline.append({"$skip": skip})

    return pipeline


def get_search_media_cursor(collection: AsyncIOMotorCollection, medium_type: MediumType, query: str, *,
                            language: Language,
                            dubbed: bool,
                            group: bool,
                            skip: int = None,
                            limit: int = None) -> AsyncIOMotorCommandCursor:
    pipeline = [
        {"$match": {
            "$text": {"$search": query},
            "medium_type": medium_type.value,
            "language": language.value,
            "dubbed": dubbed,
        }},
        {"$project": {
            "_id": False,
            "item": "$$ROOT",
            "search_relevance": {"$meta": "textScore"},
        }},
    ]

    if group:
        pipeline.append({"$group": {
            "_id": "$item.medium_id",
            "item": {"$push": "$item"},
            "search_relevance": {"$max": "$search_relevance"}
        }})

    pipeline.append({"$sort": {
        "search_relevance": DESCENDING,
    }})

    pipeline.extend(_pipeline_limit_and_skip(limit, skip))

    return collection.aggregate(pipeline)


def get_media_by_title_cursor(collection: AsyncIOMotorCollection, medium_type: MediumType, title: str, *,
                              language: Language,
                              dubbed: bool,
                              group: bool,
                              skip: int = None,
                              limit: int = None) -> AsyncIOMotorCommandCursor:
    pipeline = [{"$match": {
        "medium_type": medium_type.value,
        "language": language.value,
        "dubbed": dubbed,
        "$or": [
            {"title": title},
            {"aliases": title},
        ]
    }}]

    if group:
        pipeline.append({"$group": {
            "_id": "$medium_id",
            "items": {"$push": "$$ROOT"}
        }})

    pipeline.extend(_pipeline_limit_and_skip(limit, skip))

    return collection.aggregate(pipeline)


@overload
async def map_search_item_tuple(iterable: AIterable[Dict[str, Any]], *,
                                ignore_exceptions: bool) -> AsyncIterator[SearchItem[Dict[str, Any]]]:
    ...


@overload
async def map_search_item_tuple(iterable: AIterable[Dict[str, Any]], *,
                                ignore_exceptions: bool,
                                callback: Callable[[Dict[str, Any]], T]) -> AsyncIterator[SearchItem[T]]:
    ...


async def map_search_item_tuple(iterable: AIterable[Dict[str, Any]], *,
                                ignore_exceptions: bool,
                                callback: Callable[[Dict[str, Any]], T] = None) -> AsyncIterator[SearchItem[T]]:
    async for doc in aiter(iterable):
        try:
            raw_item = doc["item"]
            search_relevance: float = doc["search_relevance"]
        except KeyError as e:
            if ignore_exceptions:
                log.warning(f"Illegal document received (suppressed): {doc}\n{e!r}")
                continue
            else:
                raise e

        if callback is not None:
            try:
                item = callback(raw_item)
            except Exception as e:
                if not ignore_exceptions:
                    raise e
            else:
                yield SearchItem(item, search_relevance)
        else:
            yield SearchItem(raw_item, search_relevance)


def map_load_media(iterable: AIterable[Dict[str, Any]], group: bool, *, ignore_exceptions: bool = True) -> AsyncIterator[SearchItem[MediumData]]:
    if group:
        callback = medium_group_from_document
    else:
        callback = medium_from_document

    # noinspection PyTypeChecker
    return map_search_item_tuple(iterable, ignore_exceptions=ignore_exceptions, callback=callback)


async def search_media(collection: AsyncIOMotorCollection, medium_type: MediumType, query: str, *,
                       language: Language,
                       dubbed: bool,
                       group: bool = True,
                       page: int = 0,
                       items_per_page: int = 20) -> List[SearchItem[MediumData]]:
    cursor = get_search_media_cursor(collection, medium_type, query,
                                     language=language, dubbed=dubbed,
                                     group=group,
                                     skip=page * items_per_page,
                                     limit=items_per_page)

    return await alist(map_load_media(cursor, group))


async def map_load_medium(iterable: AIterable[Dict[str, Any]], group: bool, *, ignore_exceptions: bool = True) -> AsyncIterator[MediumData]:
    async for doc in aiter(iterable):
        try:
            if group:
                medium = medium_group_from_document(doc["items"])
            else:
                medium = medium_from_document(doc)
        except Exception as e:
            if ignore_exceptions:
                log.info(f"suppressed exception while handling: {doc}\n{e!r}")
            else:
                raise e
        else:
            yield medium


async def get_media_by_title(collection: AsyncIOMotorCollection, medium_type: MediumType, title: str, *,
                             language: Language,
                             dubbed: bool,
                             group: bool = True,
                             page: int = 0,
                             items_per_page: int = 20) -> List[MediumData]:
    cursor = get_media_by_title_cursor(collection, medium_type, title,
                                       language=language, dubbed=dubbed,
                                       group=group,
                                       skip=page * items_per_page,
                                       limit=items_per_page)

    return await alist(map_load_medium(cursor, group))
