import asyncio
import importlib
import logging
from contextlib import suppress
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Set, Type, cast

from grobber.exceptions import UIDUnknown
from grobber.languages import Language
from grobber.locals import anime_collection
from grobber.telemetry import SEARCH_SOURCE_COUNTER
from grobber.uid import UID
from grobber.utils import AIterable, aiter, anext
from ..models import SearchResult, SourceAnime

log = logging.getLogger(__name__)

_SOURCES = ["gogoanime", "nineanime", "vidstreaming"]
SOURCES: Dict[str, Type[SourceAnime]] = {}


def register_source(anime: Type[SourceAnime]):
    SOURCES[anime.get_qualcls().lower()] = anime


def get_source(source_id: str) -> Type[SourceAnime]:
    source_id = source_id.rsplit(".", 1)[-1]
    return SOURCES[source_id.lower()]


def _load_sources():
    for SRC in _SOURCES:
        importlib.import_module("." + SRC, __name__)


_load_sources()
log.info(f"Using Sources: {', '.join(source.__qualname__ for source in SOURCES.values())}")

CACHE: Set[SourceAnime] = set()


async def save_anime(anime: SourceAnime, *, silent: bool = False) -> None:
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


def track_in_cache(anime: SourceAnime) -> None:
    CACHE.add(anime)


async def build_anime_from_doc(uid: str, doc: Dict[str, Any]) -> SourceAnime:
    source_id = doc["cls"]

    try:
        cls = get_source(source_id)
    except KeyError:
        log.warning(f"couldn't find source for {uid}: {source_id}")
        await delete_anime(uid)
        raise UIDUnknown(uid)

    doc["id"] = uid
    anime = cls.from_state(doc)
    track_in_cache(anime)
    return anime


async def build_animes_from_docs(docs: AIterable[Dict[str, Any]]) -> AsyncIterator[Optional[SourceAnime]]:
    async for doc in aiter(docs):
        try:
            uid: str = doc["_id"]
        except KeyError:
            continue

        with suppress(UIDUnknown):
            yield await build_anime_from_doc(uid, doc)


async def get_anime(uid: UID) -> Optional[SourceAnime]:
    doc = await anime_collection.find_one(uid)
    if doc:
        return await build_anime_from_doc(uid, doc)
    return None


async def get_animes(uids: Iterable[UID]) -> Dict[UID, SourceAnime]:
    cursor = anime_collection.find({"_id": {"$in": list(uids)}})

    res = {}
    async for doc in cursor:
        uid = doc["_id"]
        try:
            anime = await build_anime_from_doc(uid, doc)
        except UIDUnknown:
            pass
        else:
            res[uid] = anime

    return res


async def get_animes_by_title(title: str, *, language=Language.ENGLISH, dubbed=False) -> AsyncIterator[SourceAnime]:
    cursor = anime_collection.find({"title": title, f"language{SourceAnime._SPECIAL_MARKER}": language.value, "is_dub": dubbed})
    async for doc in cursor:
        try:
            yield await build_anime_from_doc(doc["_id"], doc)
        except UIDUnknown as e:
            title = doc.get("title") or doc.get("_id") or "unknown"
            log.debug(f"ignoring {title} because: {e}")
            continue


async def get_anime_by_title(title: str, *, language=Language.ENGLISH, dubbed=False) -> Optional[SourceAnime]:
    return await anext(get_animes_by_title(title, language=language, dubbed=dubbed), None)


async def search_anime(query: str, *, language=Language.ENGLISH, dubbed=False) -> AsyncIterator[SearchResult]:
    # noinspection PyTypeChecker
    sources: List[AsyncIterator[SearchResult]] = [source.search(query, language=language, dubbed=dubbed) for source in SOURCES.values()]

    def waiter(src):
        async def wrapped():
            try:
                res = await anext(src)
            except Exception as e:
                return e, src

            res = cast(SearchResult, res)
            # noinspection PyUnresolvedReferences
            SEARCH_SOURCE_COUNTER.labels(res.anime.source_id).inc()
            log.debug(f"got search result from {src.__qualname__}: {res}")

            return res, src

        return asyncio.ensure_future(wrapped())

    waiting_sources = {waiter(source) for source in sources}

    def handle_result(result, source) -> bool:
        if isinstance(result, StopAsyncIteration):
            log.debug(f"{source.__qualname__} exhausted")
        elif isinstance(result, Exception):
            log.error(f"{source.__qualname__} failed to yield a search result", exc_info=result)
        else:
            waiting_sources.add(waiter(source))
            track_in_cache(result.anime)
            return True

        return False

    log.info(f"searching first batch: {query} {language.value}_{'dub' if dubbed else 'sub'}")
    batch_results = 0
    # give 3 seconds for the first batch. This should stop results from being dominated by one source only.
    done_sources, waiting_sources = await asyncio.wait(waiting_sources, return_when=asyncio.ALL_COMPLETED, timeout=5)
    for done in done_sources:
        result, source = done.result()
        if handle_result(result, source):
            batch_results += 1
            yield result

    log.info(f"entering free for all after {batch_results} result(s) from first batch")

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
