import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_MONGO_DB_NAME = os.getenv("MONGO_DB", "MyAnimeStream")

mongo_client: AsyncIOMotorClient = AsyncIOMotorClient(_MONGO_URI)
db: AsyncIOMotorDatabase = mongo_client[_MONGO_DB_NAME]

anime_collection: AsyncIOMotorCollection = db["anime"]

url_pool_collection: AsyncIOMotorCollection = db["url_pool"]
