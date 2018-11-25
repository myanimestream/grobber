import importlib
import logging
from itertools import chain, zip_longest
from typing import Dict, Iterator, Optional, Set, Type

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


def save_dirty() -> None:
    num_saved = 0
    for anime in CACHE:
        if anime.dirty:
            num_saved += 1
            anime_collection.update_one({"_id": anime.uid}, {"$set": anime.state}, upsert=True)
    log.debug(f"Saved {num_saved} dirty out of {len(CACHE)} cached anime")
    CACHE.clear()


def delete_anime(uid: str) -> None:
    log.info(f"deleting anime {uid}...")
    anime_collection.delete_one(dict(_id=uid))


def get_anime(uid: UID) -> Optional[Anime]:
    doc = anime_collection.find_one(uid)
    if doc:
        try:
            cls = SOURCES[doc["cls"]]
        except KeyError:
            log.warning(f"couldn't find source for {uid}: {doc['cls']}")
            delete_anime(uid)
            raise UIDUnknown(uid)

        anime = cls.from_state(doc)
        CACHE.add(anime)
        return anime


def search_anime(query: str, dub=False) -> Iterator[SearchResult]:
    sources = [source.search(query, dub=dub) for source in SOURCES.values()]
    result_zip = zip_longest(*sources)
    result_iter = chain(*result_zip)

    for result in result_iter:
        if result is None:
            continue

        anime = result.anime
        CACHE.add(anime)
        yield result
