import asyncio
import logging
from typing import cast

import quart
from quart import Blueprint, Request, Response, redirect, request

from grobber import locals, query
from grobber.exceptions import InvalidRequest
from grobber.index_scraper import medium_to_dict, search_media
from grobber.uid import MediumType, UID
from grobber.utils import create_response, external_url_for

request = cast(Request, request)

log = logging.getLogger(__name__)

anime_blueprint = Blueprint("anime", __name__, url_prefix="/anime")


@anime_blueprint.route("/search/")
async def search() -> Response:
    search_results = await query.search_anime()
    results = await asyncio.gather(*(a.to_dict() for a in search_results))

    return create_response(anime=results)


@anime_blueprint.route("/quicksearch/")
async def quick_search() -> Response:
    try:
        search_query = request.args.get("query")
    except Exception:
        search_query = None

    if not search_query:
        raise InvalidRequest("Please specify a query")

    try:
        page = request.args.get("page", type=int)
    except Exception:
        page = 0

    if not 0 <= page < 30:
        raise InvalidRequest("Page must be between 0 and 29")

    try:
        items_per_page = request.args.get("results", type=int)
    except Exception:
        items_per_page = 20

    language, dubbed, group = query.get_lookup_spec()

    results = await search_media(locals.source_index_collection, MediumType.ANIME, search_query,
                                 language=language,
                                 dubbed=dubbed,
                                 group=group,
                                 page=page,
                                 items_per_page=items_per_page)
    media_result_data = []

    for search_item in results:
        try:
            data = medium_to_dict(search_item.item)
        except Exception:
            log.exception(f"Couldn't convert medium to dict (silenced): {search_item}")
            continue

        data["episodes"] = data["episode_count"]
        data["media_id"] = search_item.item.medium_id

        media_result_data.append({
            "anime": data,
            "certainty": search_item.score
        })

    return create_response(anime=media_result_data)


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
