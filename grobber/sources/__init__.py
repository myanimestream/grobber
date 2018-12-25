import asyncio
import importlib
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Type

from ..exceptions import UIDUnknown
from ..languages import Language
from ..locals import anime_collection
from ..models import Anime, SearchResult, UID
from ..utils import anext

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
    if not CACHE:
        return

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


async def build_anime_from_doc(uid: str, doc: Dict[str, Any]) -> Anime:
    try:
        cls = SOURCES[doc["cls"]]
    except KeyError:
        log.warning(f"couldn't find source for {uid}: {doc['cls']}")
        await delete_anime(uid)
        raise UIDUnknown(uid)

    anime = cls.from_state(doc)
    CACHE.add(anime)
    return anime


async def get_anime(uid: UID) -> Optional[Anime]:
    doc = await anime_collection.find_one(uid)
    if doc:
        return await build_anime_from_doc(uid, doc)
    return None


async def get_anime_by_title(title: str, *, language=Language.ENGLISH, dubbed=False) -> Optional[Anime]:
    doc = await anime_collection.find_one({"title": title, f"language{Anime._SPECIAL_MARKER}": language.value, "is_dub": dubbed})
    if doc:
        return await build_anime_from_doc(doc["_id"], doc)

    return None


async def search_anime(query: str, *, language=Language.ENGLISH, dubbed=False) -> AsyncIterator[SearchResult]:
    sources: List[AsyncIterator[SearchResult]] = [source.search(query, language=language, dubbed=dubbed) for source in SOURCES.values()]

    def waiter(src):
        async def wrapped():
            try:
                res = await anext(src)
            except Exception as e:
                res = e
            return res, src

        return asyncio.ensure_future(wrapped())

    waiting_sources = {waiter(source) for source in sources}

    while waiting_sources:
        done: asyncio.Future
        (done, *_), waiting_sources = await asyncio.wait(waiting_sources, return_when=asyncio.FIRST_COMPLETED)

        result, source = done.result()

        if isinstance(result, StopAsyncIteration):
            log.debug(f"{source} exhausted")
        elif isinstance(result, Exception):
            log.exception(f"{source} failed to yield a search result!")
        else:
            waiting_sources.add(waiter(source))
            CACHE.add(result.anime)
            yield result
