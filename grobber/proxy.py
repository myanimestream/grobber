import os
from functools import partial
from operator import itemgetter

from flask import g, request
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from werkzeug.local import LocalProxy

_MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
_MONGO_DB_NAME = os.getenv("MONGO_DB", "MyAnimeStream")


def teardown():
    if hasattr(g, "mongo_client"):
        g.mongo_client.close()


def _requests_dub() -> bool:
    val = request.args.get("dub")
    if val is None or val.lower() in ("0", "false", "f", "no"):
        return False
    return True


def _mongo_client() -> MongoClient:
    if not hasattr(g, "mongo_client"):
        g.mongo_client = MongoClient(_MONGO_URI)
    return g.mongo_client


requests_dub: bool = LocalProxy(_requests_dub)

mongo_client: MongoClient = LocalProxy(_mongo_client)
db: Database = LocalProxy(partial(itemgetter(_MONGO_DB_NAME), mongo_client))
anime_collection: Collection = LocalProxy(partial(itemgetter("anime"), db))
user_collection: Collection = LocalProxy(partial(itemgetter("users"), db))
changelog_collection: Collection = LocalProxy(partial(itemgetter("changelog"), db))
url_pool_collection: Collection = LocalProxy(partial(itemgetter("url_pool"), db))
