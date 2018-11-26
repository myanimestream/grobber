import asyncio
import importlib
import logging
from typing import AsyncIterator, Dict, Optional, Set, Type

from motor.motor_asyncio import AsyncIOMotorCollection

from ..exceptions import UIDUnknown
from ..models import Anime, SearchResult, UID
from ..proxy import anime_collection

log = logging.getLogger(__name__)

_SOURCES = ["gogoanime", "masteranime"]
SOURCES: Dict[str, Type[Anime]] = {}


def register_source(anime: Type[Anime]):
    SOURCES[f"{anime.__module__}.{anime.__qualname__}"] = anime


def _load_sources():
    for SRC in _SOURCES:
        importlib.import_module("." + SRC, __name__)


_load_sources()
log.info(f"Using Sources: {SOURCES.keys()}")

CACHE: Set[Anime] = set()


async def save_dirty(collection: AsyncIOMotorCollection = None) -> None:
    collection = collection or anime_collection

    num_saved = 0
    coros = []
    for anime in CACHE:
        if anime.dirty:
            num_saved += 1
            coro = collection.update_one({"_id": await anime.uid}, {"$set": anime.state}, upsert=True)
            coros.append(coro)

    await asyncio.gather(*coros)
    log.debug(f"Saved {num_saved} dirty out of {len(CACHE)} cached anime")
    CACHE.clear()


async def delete_anime(uid: str) -> None:
    log.info(f"deleting anime {uid}...")
    await anime_collection.delete_one(dict(_id=uid))


async def get_anime(uid: UID) -> Optional[Anime]:
    doc = await anime_collection.find_one(uid)
    if doc:
        try:
            cls = SOURCES[doc["cls"]]
        except KeyError:
            log.warning(f"couldn't find source for {uid}: {doc['cls']}")
            await delete_anime(uid)
            raise UIDUnknown(uid)

        anime = cls.from_state(doc)
        CACHE.add(anime)
        return anime


async def search_anime(query: str, dub=False) -> AsyncIterator[SearchResult]:
    sources = [source.search(query, dub=dub) for source in SOURCES.values()]

    while sources:
        for source in reversed(sources):
            try:
                result = await source.__anext__()
            except StopAsyncIteration:
                log.debug(f"{source} exhausted")
                sources.remove(source)
            else:
                CACHE.add(result.anime)
                yield result
