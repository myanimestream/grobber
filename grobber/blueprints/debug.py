from datetime import datetime, timedelta

from quart import Blueprint, Response, request

from .. import sources, streams
from ..exceptions import *
from ..models import UID
from ..request import Request
from ..utils import create_response

debug_blueprint = Blueprint("debug", __name__, url_prefix="/debug")


@debug_blueprint.route("/extract")
async def extract_stream() -> Response:
    url = request.args.get("url")
    if not url:
        raise InvalidRequest("No url parameter specified")

    stream = await streams.get_stream(Request(url)).__anext__()
    if not stream:
        raise StreamNotFound()

    await stream.preload_attrs(recursive=True)
    return create_response(stream.state)


@debug_blueprint.route("/expire/<UID:uid>")
async def expire_anime(uid: UID) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    anime._last_update = datetime.now() - timedelta(seconds=anime.EXPIRE_TIME)
    anime.dirty = True
    return create_response()
