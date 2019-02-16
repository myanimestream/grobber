import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel, TEXT
from quart.local import LocalProxy

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
search_results_collection: AsyncIOMotorCollection = LocalProxy(lambda: db["search_results"])

url_pool_collection: AsyncIOMotorCollection = LocalProxy(lambda: db["url_pool"])


def before_serving():
    anime_collection.create_indexes([
        IndexModel([("title", ASCENDING), ("language", ASCENDING), ("is_dub", ASCENDING)], name="Query Index")
    ])

    search_results_collection.create_indexes([
        IndexModel([("query", TEXT)], name="Query Search"),
        IndexModel([("created", ASCENDING)], name="Expire after a month", expireAfterSeconds=60 * 60 * 24 * 30)
    ])
