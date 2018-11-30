from quart import Blueprint, Response

from ..utils import *

users = Blueprint("users", __name__, url_prefix="/user")


@users.route("/register/")
async def register_user() -> Response:
    # TODO create user and accept existing data
    return create_response()