import asyncio
import importlib
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Type

from grobber.exceptions import UIDUnknown
from grobber.languages import Language
from grobber.locals import anime_collection
from grobber.uid import UID
from grobber.utils import anext
from ..models import Anime, SearchResult

log = logging.getLogger(__name__)

_SOURCES = ["gogoanime", "masteranime", "nineanime", "vidstreaming"]
SOURCES: Dict[str, Type[Anime]] = {}


def register_source(anime: Type[Anime]):
    SOURCES[anime.__qualname__] = anime


def _load_sources():
    for SRC in _SOURCES:
        importlib.import_module("." + SRC, __name__)


_load_sources()
log.info(f"Using Sources: {', '.join(source.__qualname__ for source in SOURCES.values())}")

CACHE: Set[Anime] = set()


async def save_anime(anime: Anime, *, silent: bool = False) -> None:
    try:
        uid = await anime.uid
        await anime_collection.update_one({"_id": uid}, {"$set": anime.state}, upsert=True)
    except Exception as e:
        if silent:
            log.exception(f"Couldn't save anime {anime!r}: {e}")
        else:
            raise e


async def save_dirty() -> None:
    if not CACHE:
        return

    num_saved = 0

    coros = []
    for anime in CACHE:
        if anime.dirty:
            num_saved += 1
            coros.append(save_anime(anime, silent=True))

    await asyncio.gather(*coros)
    log.debug(f"Saved {num_saved} dirty out of {len(CACHE)} cached anime")
    CACHE.clear()


async def delete_anime(uid: str) -> None:
    log.info(f"deleting anime {uid}...")
    await anime_collection.delete_one(dict(_id=uid))


async def build_anime_from_doc(uid: str, doc: Dict[str, Any]) -> Anime:
    *_, name = doc["cls"].rsplit(".", 1)

    try:
        cls = SOURCES[name]
    except KeyError:
        log.warning(f"couldn't find source for {uid}: {name}")
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


async def get_animes_by_title(title: str, *, language=Language.ENGLISH, dubbed=False) -> AsyncIterator[Anime]:
    cursor = anime_collection.find({"title": title, f"language{Anime._SPECIAL_MARKER}": language.value, "is_dub": dubbed})
    async for doc in cursor:
        yield await build_anime_from_doc(doc["_id"], doc)


async def get_anime_by_title(title: str, *, language=Language.ENGLISH, dubbed=False) -> Optional[Anime]:
    return await anext(get_animes_by_title(title, language=language, dubbed=dubbed), None)


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

    def handle_result(result, source) -> bool:
        if isinstance(result, StopAsyncIteration):
            log.debug(f"{source} exhausted")
        elif isinstance(result, Exception):
            log.error(f"{source} failed to yield a search result", exc_info=result)
        else:
            waiting_sources.add(waiter(source))
            CACHE.add(result.anime)
            return True

        return False

    log.debug("searching first batch")
    batch_results = 0
    # give 3 seconds for the first batch. This should stop results from being dominated by one source only.
    done_sources, waiting_sources = await asyncio.wait(waiting_sources, return_when=asyncio.ALL_COMPLETED, timeout=3)
    for done in done_sources:
        result, source = done.result()
        if handle_result(result, source):
            batch_results += 1
            yield result

    log.debug(f"entering free for all after {batch_results} result(s) from first batch")

    # and from here on out it's free for all
    while waiting_sources:
        # not sure whether FIRST_COMPLETED ever returns more than one future in the done set, but just in case!
        # at least it seems like there can be multiple futures in the done set!
        done_sources, waiting_sources = await asyncio.wait(waiting_sources, return_when=asyncio.FIRST_COMPLETED)
        for done in done_sources:
            result, source = done.result()
            if handle_result(result, source):
                yield result

    log.info("All sources exhausted")
