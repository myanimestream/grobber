from typing import Any, Dict

from quart import Blueprint, Response, render_template, request

from .. import sources
from ..exceptions import UIDUnknown
from ..models import Episode, UID
from ..utils import *

templates = Blueprint("templates", __name__, url_prefix="/templates")


async def player_template_kwargs(uid: str, index: int, episode: Episode) -> Dict[str, Any]:
    stream = await episode.stream
    links = await stream.links if stream else None
    return dict(sources=links, host_url=await episode.host_url, uid=uid, index=index)


@templates.route("/player/<UID:uid>/<int:index>")
async def player(uid: UID, index: int) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        return error_response(UIDUnknown(uid))

    episode = await anime.get(index)
    html = await render_template("player.html", **await player_template_kwargs(uid, index, episode))
    return Response(html)


@templates.route("/mal/episode/<UID:uid>")
async def mal_episode_list(uid: UID) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        return error_response(UIDUnknown(uid))

    offset = request.args.get("offset", type=int, default=0)
    html = await render_template("mal/episode_list.html", episode_count=await anime.episode_count, offset=offset)
    return Response(html)


@templates.route("/mal/episode/<UID:uid>/<int:index>")
async def mal_episode(uid: UID, index: int) -> Response:
    anime = await sources.get_anime(uid)
    if not anime:
        return error_response(UIDUnknown(uid))

    episode = await anime.get(index)

    html = await render_template("mal/episode.html", episode_count=await anime.episode_count,
                                 **await player_template_kwargs(uid, index, episode))
    return Response(html)


@templates.route("/mal/settings")
async def mal_settings():
    # MultiDicts have Lists for values (because there can be multiple values for the same key but we don't want that, thus the "to_dict"
    context = request.args.to_dict()
    html = await render_template("mal/settings.html", **context)
    return Response(html)
