import asyncio
import logging
from operator import attrgetter

import quart
from quart import Blueprint, Response, redirect, request

from .. import proxy, sources
from ..exceptions import InvalidRequest, UIDUnknown
from ..models import Anime, UID
from ..utils import *

log = logging.getLogger(__name__)

anime_blueprint = Blueprint("anime", __name__, url_prefix="/anime")


@anime_blueprint.route("/search/<query>")
async def search(query: str) -> Response:
    num_results = request.args.get("results", type=int, default=1)
    if not (0 < num_results <= 10):
        raise InvalidRequest(f"Can only request up to 10 results (not {num_results})")

    result_iter = sources.search_anime(query, dub=proxy.requests_dub)

    results_pool = []
    async for result in result_iter:
        if len(results_pool) >= num_results:
            break

        results_pool.append(result)

    results = sorted(results_pool, key=attrgetter("certainty"), reverse=True)[:min(num_results, 3)]
    ser_results = list(await asyncio.gather(*(result.to_dict() for result in results)))

    ser_results.sort(key=lambda item: (round(item["certainty"], 2), item["anime"]["episodes"]), reverse=True)

    return create_response(anime=ser_results[:num_results])


@anime_blueprint.route("/episode-count", methods=("POST",))
async def get_anime_episode_count() -> Response:
    anime_uids = request.json
    if not isinstance(anime_uids, list):
        raise InvalidRequest("Body needs to contain a list of uids!")

    if len(anime_uids) > 30:
        raise InvalidRequest(f"Too many anime requested, max is 30! ({len(anime_uids)})")

    anime = filter(None, await asyncio.gather(*(sources.get_anime(uid) for uid in anime_uids)))

    async def get_pair(a: Anime) -> (str, int):
        return await a.uid, await a.episode_count

    anime_counts = await asyncio.gather(*(get_pair(a) for a in anime))
    return create_response(anime=dict(anime_counts))


@anime_blueprint.route("/<UID:uid>")
async def get_anime(uid: UID) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    return create_response(await anime.to_dict())


@anime_blueprint.route("/<UID:uid>/preload")
async def preload_anime(uid: UID) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    await anime.preload_attrs(recursive=False)

    return create_response(await anime.to_dict())


@anime_blueprint.route("/<UID:uid>/state")
async def get_anime_state(uid: UID) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    return create_response(data=anime.state)


@anime_blueprint.route("/<UID:uid>/<int:index>")
async def get_episode(uid: UID, index: int) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = await anime.get(index)

    return create_response(await episode.to_dict())


@anime_blueprint.route("/<UID:uid>/<int:index>/preload")
async def preload_episode(uid: UID, index: int) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = await anime.get(index)

    await episode.preload_attrs(recursive=True)

    return create_response(await episode.to_dict())


@anime_blueprint.route("/<UID:uid>/<int:index>/state")
async def get_episode_state(uid: UID, index: int) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = await anime.get(index)
    return create_response(data=episode.state)


@anime_blueprint.route("/<UID:uid>/<int:index>/poster")
async def get_episode_poster(uid: UID, index: int) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = await anime.get(index)
    poster = await episode.poster or external_url_for("static", filename="images/default_poster")
    return redirect(poster)


@anime_blueprint.route("/<UID:uid>/<int:index>/stream")
async def get_episode_stream(uid: UID, index: int) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        raise UIDUnknown(uid)

    episode = await anime.get(index)
    stream = await episode.stream
    if stream:
        url = next(iter(await stream.links), None)
    else:
        url = None

    if not url:
        quart.abort(404)

    return redirect(url)
