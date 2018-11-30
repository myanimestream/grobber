import asyncio
import logging

import quart
from quart import Blueprint, Response, redirect, request

from .. import query, sources
from ..exceptions import InvalidRequest
from ..models import Anime, UID
from ..utils import *

log = logging.getLogger(__name__)

anime_blueprint = Blueprint("anime", __name__, url_prefix="/anime")


@anime_blueprint.route("/search/")
async def search() -> Response:
    anime = await query.search_anime()
    results = [await a.to_dict() for a in anime]

    return create_response(anime=results)


@anime_blueprint.route("/episode-count/", methods=("POST",))
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


@anime_blueprint.route("/")
async def get_anime_info() -> Response:
    anime = await query.get_anime()
    return create_response(await anime.to_dict())


@anime_blueprint.route("/preload/")
async def preload_anime() -> Response:
    anime = await query.get_anime()
    await anime.preload_attrs(recursive=False)

    return create_response(await anime.to_dict())


@anime_blueprint.route("/state/")
async def get_anime_state() -> Response:
    anime = await query.get_anime()
    return create_response(data=anime.state)


@anime_blueprint.route("/episode/")
async def get_episode_info() -> Response:
    episode = await query.get_episode()
    return create_response(await episode.to_dict())


@anime_blueprint.route("/episode/preload/")
async def preload_episode() -> Response:
    episode = await query.get_episode()

    await episode.preload_attrs(recursive=True)

    return create_response(await episode.to_dict())


@anime_blueprint.route("/episode/state/")
async def get_episode_state() -> Response:
    episode = await query.get_episode()
    return create_response(data=episode.state)


@anime_blueprint.route("/stream/")
async def get_stream_info() -> Response:
    stream = await query.get_stream()

    return create_response(await stream.to_dict())


@anime_blueprint.route("/poster/<UID:uid>/<int:index>/")
async def episode_poster(uid: UID, index: int) -> Response:
    episode = await query.get_episode(uid=uid, episode_index=index)
    poster = await episode.poster or external_url_for("static", filename="images/default_poster")
    return redirect(poster)


@anime_blueprint.route("/source/<UID:uid>/<int:episode_index>/<int:stream_index>/")
async def episode_stream_source(uid: UID, episode_index: int, stream_index: int) -> Response:
    stream = await query.get_stream(uid=uid, episode_index=episode_index, stream_index=stream_index)
    links = await stream.links

    if links:
        return redirect(links[0])
    else:
        quart.abort(404)


@anime_blueprint.route("/source/<UID:uid>/<int:episode_index>/")
async def episode_source(uid: UID, episode_index: int) -> Response:
    episode = await query.get_episode(uid=uid, episode_index=episode_index)

    stream = await episode.stream
    links = await stream.links if stream else None

    if links:
        return redirect(links[0])
    else:
        quart.abort(404)
