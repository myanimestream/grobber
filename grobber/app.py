import logging
import os

import raven
from quart import Quart, Response, redirect
from raven.conf import setup_logging
from raven.handlers.logging import SentryHandler

from . import __info__, sources
from .blueprints import *
from .exceptions import GrobberException
from .models import UIDConverter
from .utils import *

log = logging.getLogger(__name__)

app = Quart("grobber", static_url_path="/")
sentry_client = raven.Client(release=__info__.__version__)
sentry_handler = SentryHandler(sentry_client)
sentry_handler.setLevel(logging.ERROR)
setup_logging(sentry_handler)

app.url_map.converters["UID"] = UIDConverter

app.register_blueprint(anime_blueprint)
app.register_blueprint(templates)
app.register_blueprint(users)
app.register_blueprint(debug_blueprint)

host_url = os.getenv("HOST_URL")
if host_url:
    app.config["HOST_URL"] = add_http_scheme(host_url)

app.config["USERSCRIPT_LOCATION"] = os.getenv("USERSCRIPT_LOCATION", "js/myanimestream.user.js")

log.info(f"grobber version {__info__.__version__} running!")


@app.errorhandler(GrobberException)
def handle_grobber_exception(exc: GrobberException) -> Response:
    return error_response(exc)


@app.teardown_appcontext
def teardown_app_context(*_):
    do_later(sources.save_dirty())


@app.after_request
async def after_request(response: Response) -> Response:
    response.headers["grobber-version"] = __info__.__version__
    return response


@app.context_processor
async def inject_jinja_globals():
    return dict(url_for=external_url_for)


@app.route("/download")
async def get_userscript() -> Response:
    return redirect(app.config["USERSCRIPT_LOCATION"])
