import asyncio
import logging
from operator import attrgetter

import quart
from quart import Blueprint, Response, redirect, request

from .. import languages, sources
from ..exceptions import InvalidRequest, UIDUnknown
from ..models import Anime, Episode, Stream, UID
from ..utils import *

log = logging.getLogger(__name__)

anime_blueprint = Blueprint("anime", __name__, url_prefix="/anime")


@anime_blueprint.route("/search/")
async def search() -> Response:
    args = request.args

    query = args.get("query")
    if not query:
        raise InvalidRequest("No query specified")

    num_results = args.get("results", type=int, default=1)
    if not (0 < num_results <= 10):
        raise InvalidRequest(f"Can only request up to 10 results (not {num_results})")

    dubbed = args.get("dubbed", default=False, type=fuzzy_bool)
    language = args.get("language")
    language = languages.get_lang(language) if language else languages.Language.ENGLISH

    result_iter = sources.search_anime(query, dubbed=dubbed, language=language)

    results_pool = []
    async for result in result_iter:
        if len(results_pool) >= num_results:
            break

        results_pool.append(result)

    results = sorted(results_pool, key=attrgetter("certainty"), reverse=True)[:min(num_results, 3)]
    ser_results = list(await asyncio.gather(*(result.to_dict() for result in results)))

    ser_results.sort(key=lambda item: (round(item["certainty"], 2), item["anime"]["episodes"]), reverse=True)

    return create_response(anime=ser_results[:num_results])


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


async def get_user():
    pass


async def get_anime(*, uid: UID = None) -> Anime:
    if not uid:
        args = request.args
        uid = args.get("uid", type=UID)

    if uid:
        anime = await sources.get_anime(uid)
        if not anime:
            raise UIDUnknown(uid)
    else:
        name = args.get("anime")
        if not name:
            raise InvalidRequest("Please either specify \"uid\" or \"anime\". If you only know the title of the anime, not its uid, use \"anime\"")

        user = get_user()

        # get uid for name

        if not uid:
            pass

        anime = await sources.get_anime(uid)

    return anime


@anime_blueprint.route("/")
async def get_anime_info() -> Response:
    anime = await get_anime()
    return create_response(await anime.to_dict())


@anime_blueprint.route("/preload/")
async def preload_anime() -> Response:
    anime = await get_anime()
    await anime.preload_attrs(recursive=False)

    return create_response(await anime.to_dict())


@anime_blueprint.route("/state/")
async def get_anime_state() -> Response:
    anime = await get_anime()
    return create_response(data=anime.state)


async def get_episode(*, episode_index: int = None, **kwargs) -> Episode:
    if episode_index is None:
        try:
            episode_index = request.args.get("episode", type=int)
        except TypeError:
            episode_index = None

        if episode_index is None:
            raise InvalidRequest("No episode index specified!")

    return await (await get_anime(**kwargs)).get(episode_index)


@anime_blueprint.route("/episode/")
async def get_episode_info() -> Response:
    episode = await get_episode()
    return create_response(await episode.to_dict())


@anime_blueprint.route("/episode/preload/")
async def preload_episode() -> Response:
    episode = await get_episode()

    await episode.preload_attrs(recursive=True)

    return create_response(await episode.to_dict())


@anime_blueprint.route("/episode/state/")
async def get_episode_state() -> Response:
    episode = await get_episode()
    return create_response(data=episode.state)


async def get_stream(*, stream_index: int = None, **kwargs) -> Stream:
    if stream_index is None:
        try:
            stream_index = request.args.get("stream", type=int)
        except TypeError:
            stream_index = None

        if stream_index is None:
            raise InvalidRequest("Stream index not specified!")

    return await (await get_episode(**kwargs)).get(stream_index)


@anime_blueprint.route("/stream/")
async def get_stream_info() -> Response:
    stream = await get_stream()

    return create_response(await stream.to_dict())


@anime_blueprint.route("/poster/<UID:uid>/<int:index>/")
async def episode_poster(uid: UID, index: int) -> Response:
    episode = await get_episode(uid=uid, episode_index=index)
    poster = await episode.poster or external_url_for("static", filename="images/default_poster")
    return redirect(poster)


@anime_blueprint.route("/source/<UID:uid>/<int:episode_index>/<int:stream_index>/")
async def episode_stream_source(uid: UID, episode_index: int, stream_index: int) -> Response:
    stream = await get_stream(uid=uid, episode_index=episode_index, stream_index=stream_index)
    links = await stream.links

    if links:
        return redirect(links[0])
    else:
        quart.abort(404)


@anime_blueprint.route("/source/<UID:uid>/<int:episode_index>/")
async def episode_source(uid: UID, episode_index: int) -> Response:
    episode = await get_episode(uid=uid, episode_index=episode_index)

    stream = await episode.stream
    links = await stream.links if stream else None

    if links:
        return redirect(links[0])
    else:
        quart.abort(404)
