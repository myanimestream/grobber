from quart import Blueprint, Response, request

from .. import locals
from ..exceptions import InvalidRequest, UserNotFound
from ..utils import *

users = Blueprint("users", __name__, url_prefix="/user")


async def store_data(username: str, name: str, data: dict) -> Response:
    data = {f"{name}.{key}": value for key, value in data.items()}
    await locals.user_collection.update_one({"_id": username},
                                            {"$setOnInsert": {"_id": username},
                                            "$set": data,
                                            "$currentDate": {"last_edit": True},
                                            "$inc": {"edits": 1}
                                            }, upsert=True)
    return create_response()


async def get_data_resp(username: str, name: str) -> Response:
    user_data = await locals.user_collection.find_one(username, projection={name: 1})
    if user_data:
        items = user_data.get(name, {})
        return create_response(**{name: items})
    else:
        return error_response(UserNotFound(username))


@users.route("/<username>/config")
async def get_user_config(username: str) -> Response:
    return await get_data_resp(username, "config")


@users.route("/<username>/config", methods=("POST",))
async def set_user_config(username: str) -> Response:
    update = await request.get_json()
    if not update:
        return error_response(InvalidRequest("Config missing"))
    return await store_data(username, "config", update)
