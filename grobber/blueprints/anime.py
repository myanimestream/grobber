import asyncio
import logging

import quart
from quart import Blueprint, Response, redirect

from .. import query
from ..uid import UID
from ..utils import create_response, external_url_for

log = logging.getLogger(__name__)

anime_blueprint = Blueprint("anime", __name__, url_prefix="/anime")


@anime_blueprint.route("/search/")
async def search() -> Response:
    search_results = await query.search_anime()
    results = await asyncio.gather(*(a.to_dict() for a in search_results))

    return create_response(anime=results)


@anime_blueprint.route("/")
async def get_anime_info() -> Response:
    anime = await query.get_anime()
    return create_response(anime=await anime.to_dict())


@anime_blueprint.route("/state/")
async def get_anime_state() -> Response:
    anime = await query.get_anime()
    return create_response(data=anime.state)


@anime_blueprint.route("/episode/")
async def get_episode_info() -> Response:
    anime = await query.get_anime()
    episode = await query.get_episode(anime=anime)

    anime_dict, episode_dict = await asyncio.gather(anime.to_dict(), episode.to_dict())

    return create_response(anime=anime_dict, episode=episode_dict)


@anime_blueprint.route("/episode/state/")
async def get_episode_state() -> Response:
    episode = await query.get_episode()
    return create_response(data=getattr(episode, "state", {}))


@anime_blueprint.route("/stream/")
async def get_stream_info() -> Response:
    anime = await query.get_anime()
    episode = await query.get_episode(anime=anime)
    stream = await query.get_stream(episode=episode)

    anime_dict, episode_dict, stream_dict = await asyncio.gather(anime.to_dict(), episode.to_dict(), stream.to_dict())
    return create_response(anime=anime_dict, episode=episode_dict, stream=stream_dict)


@anime_blueprint.route("/poster/<UID:uid>/<int:index>")
async def episode_poster(uid: UID, index: int) -> Response:
    episode = await query.get_episode(uid=uid, episode_index=index)
    poster = await episode.poster or external_url_for("static", filename="images/default_poster")
    return redirect(poster)


@anime_blueprint.route("/source/<UID:uid>/<int:episode_index>")
async def episode_source(uid: UID, episode_index: int) -> Response:
    episode = await query.get_episode(uid=uid, episode_index=episode_index)

    stream = await episode.stream
    links = await stream.links if stream else None

    if links:
        return redirect(links[0])
    else:
        quart.abort(404)
