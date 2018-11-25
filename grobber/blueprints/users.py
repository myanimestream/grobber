from flask import Blueprint, Response, request

from .. import proxy
from ..exceptions import InvalidRequest, UserNotFound
from ..utils import *

users = Blueprint("users", __name__, url_prefix="/user")


def safe_key(key: str) -> str:
    return key.replace(".", "")


def store_data(username: str, name: str, data: dict) -> Response:
    data = {f"{name}.{safe_key(key)}": value for key, value in data.items()}
    proxy.user_collection.update_one({"_id": username},
                                     {"$setOnInsert": {"_id": username},
                                      "$set": data,
                                      "$currentDate": {"last_edit": True},
                                      "$inc": {"edits": 1}
                                      }, upsert=True)
    return create_response()


def get_data_resp(username: str, name: str) -> Response:
    user_data = proxy.user_collection.find_one(username, projection={name: 1})
    if user_data:
        items = user_data.get(name, {})
        return create_response(**{name: items})
    else:
        return error_response(UserNotFound(username))


@users.route("/<username>/config")
def get_user_config(username: str) -> Response:
    return get_data_resp(username, "config")


@users.route("/<username>/config", methods=("POST",))
def set_user_config(username: str) -> Response:
    update = request.get_json()
    if not update:
        return error_response(InvalidRequest("Config missing"))
    return store_data(username, "config", update)


@users.route("/<username>/anime")
def get_all_anime(username: str) -> Response:
    return get_data_resp(username, "anime")


@users.route("/<username>/anime/<name>")
def get_anime(username: str, name: str) -> Response:
    return get_data_resp(username, "anime")


@users.route("/<username>/anime", methods=("POST",))
def set_user_episodes(username: str) -> Response:
    update = request.get_json()
    if not update:
        return error_response(InvalidRequest("Episodes missing"))
    return store_data(username, "anime", update)
