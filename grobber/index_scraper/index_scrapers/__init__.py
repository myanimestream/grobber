import asyncio
import itertools
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple, Type

import pymongo
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import IndexModel

from ..common import IndexScraper, IndexScraperCategory, get_index_scraper_category, is_index_scraper

__all__ = ["load_internal_index_scrapers", "register_index_scraper", "get_index_scrapers", "add_collection_indexes",
           "run_index_scrapers",
           "scrape_indices"]

log = logging.getLogger(__name__)

_LOADED: bool = False

INDEX_SCRAPERS: Dict[IndexScraperCategory, Set[Type[IndexScraper]]] = defaultdict(set)


def load_internal_index_scrapers() -> None:
    import inspect
    import importlib

    scrapers_dir: Path = Path(__file__).parent

    for scraper_file in scrapers_dir.iterdir():
        module_name = f".{scraper_file.stem}"
        module = importlib.import_module(module_name, package=__package__)
        scrapers: List[Tuple[str, Type[IndexScraper]]] = inspect.getmembers(module, predicate=is_index_scraper)

        for _, scraper in scrapers:
            register_index_scraper(scraper)

    global _LOADED
    _LOADED = True


def register_index_scraper(index_scraper: Type[IndexScraper]) -> None:
    category = get_index_scraper_category(index_scraper)
    INDEX_SCRAPERS[category].add(index_scraper)


def get_index_scrapers(*categories: IndexScraperCategory) -> Set[Type[IndexScraper]]:
    if not _LOADED:
        load_internal_index_scrapers()

    if categories:
        index_scraper_sets = (INDEX_SCRAPERS[category] for category in categories)
    else:
        index_scraper_sets = INDEX_SCRAPERS.values()

    return set(itertools.chain.from_iterable(index_scraper_sets))


async def add_collection_indexes(collection: AsyncIOMotorCollection) -> None:
    await collection.create_indexes([
        IndexModel([
            ("title", pymongo.TEXT),
            ("aliases", pymongo.TEXT),
            ("language", pymongo.ASCENDING),
            ("medium_type", pymongo.ASCENDING),
            ("dubbed", pymongo.ASCENDING),
        ])
    ])


async def run_index_scrapers(collection: AsyncIOMotorCollection, meta_collection: AsyncIOMotorCollection,
                             index_scrapers: Iterable[Type[IndexScraper]]) -> None:
    log.info(f"ensuring collection has indexes ({collection})")
    await add_collection_indexes(collection)

    scrapers: List[IndexScraper] = [index_scraper(collection, meta_collection) for index_scraper in index_scrapers]

    log.debug(f"starting scrape for scrapers: {scrapers}")
    await asyncio.gather(*(scraper.scrape() for scraper in scrapers))

    log.info(f"all scrapers completed: {scrapers}")


async def scrape_indices(collection: AsyncIOMotorCollection, meta_collection: AsyncIOMotorCollection, *categories: IndexScraperCategory) -> None:
    await run_index_scrapers(collection, meta_collection, get_index_scrapers(*categories))
