import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from quart import request
from quart.local import LocalProxy

_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_MONGO_DB_NAME = os.getenv("MONGO_DB", "MyAnimeStream")

mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(_MONGO_URI)
db: AsyncIOMotorDatabase = mongo_client[_MONGO_DB_NAME]
anime_collection: AsyncIOMotorCollection = db["anime"]
user_collection: AsyncIOMotorCollection = db["users"]
changelog_collection: AsyncIOMotorCollection = db["changelog"]
url_pool_collection: AsyncIOMotorCollection = db["url_pool"]


def _requests_dub() -> bool:
    val = request.args.get("dub")
    if val is None or val.lower() in ("0", "false", "f", "no"):
        return False
    return True


requests_dub: bool = LocalProxy(_requests_dub)
