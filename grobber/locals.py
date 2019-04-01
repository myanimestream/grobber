import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel
from quart.local import LocalProxy

__all__ = ["mongo_client", "db",
           "anime_collection",
           "url_pool_collection",
           "source_index_collection", "source_index_meta_collection",
           "before_serving"]

_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_MONGO_DB_NAME = os.getenv("MONGO_DB", "MyAnimeStream")

_mongo_client = None


def _get_mongo_client():
    global _mongo_client

    if not _mongo_client:
        _mongo_client = AsyncIOMotorClient(_MONGO_URI)
    return _mongo_client


mongo_client: AsyncIOMotorClient = LocalProxy(_get_mongo_client)
db: AsyncIOMotorDatabase = LocalProxy(lambda: mongo_client[_MONGO_DB_NAME])

anime_collection: AsyncIOMotorCollection = LocalProxy(lambda: db["anime"])

url_pool_collection: AsyncIOMotorCollection = LocalProxy(lambda: db["url_pool"])

source_index_collection: AsyncIOMotorClient = LocalProxy(lambda: db["source_index"])
source_index_meta_collection: AsyncIOMotorClient = LocalProxy(lambda: db["source_index_meta"])


def before_serving():
    anime_collection.create_indexes([
        IndexModel([("title", ASCENDING), ("language", ASCENDING), ("is_dub", ASCENDING)], name="Query Index"),
        IndexModel([("media_id", ASCENDING), ("language", ASCENDING), ("is_dub", ASCENDING)], name="Media ID Index"),
    ])

    from .index_scraper import add_collection_indexes
    add_collection_indexes(source_index_collection)
