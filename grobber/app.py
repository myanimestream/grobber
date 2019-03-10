# noinspection PyUnresolvedReferences
import logging
import os
from typing import cast

import sentry_sdk
from quart import Quart, Request, Response, request

from . import __info__, anime, locals, telemetry
from .blueprints import *
from .exceptions import GrobberException
from .telemetry import API_EXCEPTIONS, API_REQUESTS, INTERNAL_EXCEPTIONS
from .uid import UID
from .utils import *

request = cast(Request, request)

log = logging.getLogger(__name__)

app = Quart("grobber", static_url_path="/")

app.url_map.converters["UID"] = UID

app.register_blueprint(anime_blueprint)

host_url = os.getenv("HOST_URL")
if host_url:
    app.config["HOST_URL"] = add_http_scheme(host_url)

sentry_sdk.init(release=f"grobber@{__info__.__version__}")


@app.errorhandler(GrobberException)
def handle_grobber_exception(exc: GrobberException) -> Response:
    API_EXCEPTIONS.labels(exc.name).inc()
    return error_response(exc)


@app.errorhandler(500)
def handle_internal_exception(exc: Exception) -> Response:
    log.exception("internal error")
    INTERNAL_EXCEPTIONS.labels(type(exc).__name__).inc()
    return error_response(GrobberException(f"Internal Error: {type(exc).__qualname__}"), status_code=500)


@app.teardown_appcontext
def teardown_app_context(*_):
    anime.teardown()


@app.before_serving
async def before_serving():
    log.info(f"grobber version {__info__.__version__} running!")
    locals.before_serving()


@app.before_request
async def before_request():
    args = " ".join(f"{key}={value}" for key, value in request.args.items())
    log.info(f"{request.method} {request.endpoint or request.path} {args}")
    API_REQUESTS.labels(request.method, request.endpoint).inc()


@app.after_request
async def after_request(response: Response) -> Response:
    response.headers["Grobber-Version"] = __info__.__version__
    return response


@app.route("/dolos-info")
async def get_dolos_info() -> Response:
    return create_response(id="grobber", version=__info__.__version__)


@app.route("/metrics")
async def get_metrics() -> Response:
    metrics, content_type = telemetry.get_metrics()
    return Response(metrics, content_type=content_type)
