from flask import Blueprint, Response, request

from .. import streams
from ..exceptions import *
from ..request import Request
from ..utils import create_response

debug_blueprint = Blueprint("debug", __name__, url_prefix="/debug")


@debug_blueprint.route("/extract")
def extract_stream() -> Response:
    url = request.args.get("url")
    if not url:
        raise InvalidRequest("No url parameter specified")

    stream = next(streams.get_stream(Request(url)), None)
    if not stream:
        raise StreamNotFound()

    stream.preload_attrs(recursive=True)
    return create_response(stream.state)
