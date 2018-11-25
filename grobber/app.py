import logging
import os

import raven
from flask import Flask, Response, redirect
from raven.conf import setup_logging
from raven.contrib.flask import Sentry
from raven.handlers.logging import SentryHandler

from . import __info__, proxy, sources
from .blueprints import *
from .exceptions import GrobberException
from .models import UIDConverter
from .utils import *

log = logging.getLogger(__name__)

app = Flask("grobber", static_url_path="/")
sentry_client = raven.Client(release=__info__.__version__)
Sentry(app, sentry_client)
sentry_handler = SentryHandler(sentry_client)
sentry_handler.setLevel(logging.ERROR)
setup_logging(sentry_handler)

app.url_map.converters["UID"] = UIDConverter

app.register_blueprint(anime_blueprint)
app.register_blueprint(templates)
app.register_blueprint(users)
app.register_blueprint(forward)
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
    sources.save_dirty()
    proxy.teardown()


@app.after_request
def after_request(response: Response) -> Response:
    response.headers["grobber-version"] = __info__.__version__
    return response


@app.context_processor
def inject_jinja_globals():
    return dict(url_for=external_url_for)


@app.route("/download")
def get_userscript() -> Response:
    return redirect(app.config["USERSCRIPT_LOCATION"])
