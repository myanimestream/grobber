import asyncio
import importlib
import logging
from typing import AsyncIterator, Dict, Optional, Set, Type

from ..exceptions import UIDUnknown
from ..languages import Language
from ..locals import anime_collection, query_collection
from ..models import Anime, SearchResult, UID

log = logging.getLogger(__name__)

_SOURCES = ["gogoanime", "masteranime"]
SOURCES: Dict[str, Type[Anime]] = {}


def register_source(anime: Type[Anime]):
    SOURCES[f"{anime.__module__}.{anime.__qualname__}"] = anime


def _load_sources():
    for SRC in _SOURCES:
        importlib.import_module("." + SRC, __name__)


_load_sources()
log.info(f"Using Sources: {', '.join(source.__name__ for source in SOURCES.values())}")

CACHE: Set[Anime] = set()


async def save_dirty() -> None:
    num_saved = 0
    coros = []
    for anime in CACHE:
        if anime.dirty:
            num_saved += 1
            coro = anime_collection.update_one({"_id": await anime.uid}, {"$set": anime.state}, upsert=True)
            coros.append(coro)

    await asyncio.gather(*coros)
    log.debug(f"Saved {num_saved} dirty out of {len(CACHE)} cached anime")
    CACHE.clear()


async def delete_anime(uid: str) -> None:
    log.info(f"deleting anime {uid}...")
    await anime_collection.delete_one(dict(_id=uid))
    # delete all queries that point to this uid
    await query_collection.delete_many(dict(uid=uid))


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


async def search_anime(query: str, *, language=Language.ENGLISH, dubbed=False) -> AsyncIterator[SearchResult]:
    sources = [source.search(query, language=language, dubbed=dubbed) for source in SOURCES.values()]

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
