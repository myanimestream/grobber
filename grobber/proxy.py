import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from quart import g, request
from quart.local import LocalProxy

_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_MONGO_DB_NAME = os.getenv("MONGO_DB", "MyAnimeStream")


def _requests_dub() -> bool:
    val = request.args.get("dub")
    if val is None or val.lower() in ("0", "false", "f", "no"):
        return False
    return True


def _mongo_client() -> AsyncIOMotorClient:
    if not hasattr(g, "mongo_client"):
        g.mongo_client = AsyncIOMotorClient(_MONGO_URI)
    return g.mongo_client


requests_dub: bool = LocalProxy(_requests_dub)

# mongo_client: AsyncIOMotorClient = LocalProxy(_mongo_client)
# db: AsyncIOMotorDatabase = LocalProxy(partial(itemgetter(_MONGO_DB_NAME), mongo_client))
# anime_collection: AsyncIOMotorCollection = LocalProxy(partial(itemgetter("anime"), db))
# user_collection: AsyncIOMotorCollection = LocalProxy(partial(itemgetter("users"), db))
# changelog_collection: AsyncIOMotorCollection = LocalProxy(partial(itemgetter("changelog"), db))
# url_pool_collection: AsyncIOMotorCollection = LocalProxy(partial(itemgetter("url_pool"), db))

mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(_MONGO_URI)
db: AsyncIOMotorDatabase = mongo_client[_MONGO_DB_NAME]
anime_collection: AsyncIOMotorCollection = db["anime"]
user_collection: AsyncIOMotorCollection = db["users"]
changelog_collection: AsyncIOMotorCollection = db["changelog"]
url_pool_collection: AsyncIOMotorCollection = db["url_pool"]
