import logging
from operator import attrgetter, methodcaller

import flask
from flask import Blueprint, Response, redirect, request

from .. import proxy, sources
from ..exceptions import InvalidRequest, UIDUnknown
from ..models import UID
from ..utils import *

log = logging.getLogger(__name__)

anime_blueprint = Blueprint("anime", __name__)


@anime_blueprint.route("/search/<query>")
def search(query: str) -> Response:
    num_results = cast_argument(request.args.get("results"), int, 1)
    if not (0 < num_results <= 10):
        raise InvalidRequest(f"Can only request up to 10 results (not {num_results})")

    result_iter = sources.search_anime(query, dub=proxy.requests_dub)

    results_pool = []
    for result in result_iter:
        if len(results_pool) >= num_results:
            break

        results_pool.append(result)

    results = sorted(results_pool, key=attrgetter("certainty"), reverse=True)[:min(num_results, 3)]
    ser_results = list(thread_pool.map(methodcaller("to_dict"), results))

    ser_results.sort(key=lambda item: (round(item["certainty"], 2), item["anime"]["episodes"]), reverse=True)

    return create_response(anime=ser_results[:num_results])


@anime_blueprint.route("/anime/episode-count", methods=("POST",))
def get_anime_episode_count() -> Response:
    anime_uids = request.json
    if not isinstance(anime_uids, list):
        raise InvalidRequest("Body needs to contain a list of uids!")

    if len(anime_uids) > 30:
        raise InvalidRequest(f"Too many anime requested, max is 30! ({len(anime_uids)})")
    anime = filter(None, [sources.get_anime(uid) for uid in anime_uids])
    anime_counts = list(thread_pool.map(lambda a: (a.uid, a.episode_count), anime))
    return create_response(anime=dict(anime_counts))


@anime_blueprint.route("/anime/<UID:uid>")
def get_anime(uid: UID) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)
    return create_response(anime.to_dict())


@anime_blueprint.route("/anime/<UID:uid>/preload")
def preload_anime(uid: UID) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    anime.preload_attrs()

    return create_response(anime.to_dict())


@anime_blueprint.route("/anime/<UID:uid>/state")
def get_anime_state(uid: UID) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)
    return create_response(data=anime.state)


@anime_blueprint.route("/anime/<UID:uid>/<int:index>")
def get_episode(uid: UID, index: int) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = anime[index]

    return create_response(episode.to_dict())


@anime_blueprint.route("/anime/<UID:uid>/<int:index>/preload")
def preload_episode(uid: UID, index: int) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)
    episode = anime[index]

    episode.preload_attrs(recursive=True)

    return create_response(episode.to_dict())


@anime_blueprint.route("/anime/<UID:uid>/<int:index>/state")
def get_episode_state(uid: UID, index: int) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)
    episode = anime[index]
    return create_response(data=episode.state)


@anime_blueprint.route("/anime/<UID:uid>/<int:index>/poster")
def get_episode_poster(uid: UID, index: int) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = anime[index]
    poster = episode.poster or external_url_for("static", filename="images/default_poster")
    return redirect(poster)


@anime_blueprint.route("/anime/<UID:uid>/<int:index>/stream")
def get_episode_stream(uid: UID, index: int) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = anime[index]
    stream = episode.stream
    if stream:
        url = next(iter(stream.links), None)
    else:
        url = None

    if not url:
        return flask.abort(404)

    return redirect(url)
