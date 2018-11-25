from collections import defaultdict
from operator import attrgetter
from typing import Dict

import mistune
from flask import Blueprint, Response, render_template, request

from .. import proxy, sources
from ..exceptions import GrobberException, InvalidRequest, UIDUnknown
from ..models import UID
from ..utils import *

templates = Blueprint("templates", __name__, url_prefix="/templates")


@templates.route("/changelog/<from_version>/<to_version>")
def get_changelog(from_version: str, to_version: str) -> Response:
    try:
        from_version = Version(*map(int, from_version.split(".")))
    except ValueError:
        return error_response(InvalidRequest(f"Provided from_version doesn't match the semantic scheme ({from_version})"))
    try:
        to_version = Version(*map(int, to_version.split(".")))
    except ValueError:
        return error_response(InvalidRequest(f"Provided to_version doesn't match the semantic scheme ({to_version})"))

    cursor = proxy.changelog_collection.find({"version_num": {"$gt": from_version.version_num, "$lte": to_version.version_num}})
    documents = list(cursor)
    if not documents:
        return error_response(InvalidRequest("Nothing to display"))

    markdown = mistune.Markdown()
    categories: Dict[str, list] = defaultdict(list)
    for document in documents:
        for change in document["changes"]:
            log_type = change["type"]
            text = markdown(change["text"])
            priority = change.get("priority", 0)
            version = Version.from_version_num(document["version_num"])
            categories[log_type].insert(0, ChangelogEntry(text, priority, version, document["release"]))
    for category_changes in categories.values():
        category_changes.sort(key=attrgetter("priority"), reverse=True)
    return render_template("changelog.html", categories=categories, from_version=from_version, to_version=to_version)


@templates.route("/player/<UID:uid>/<int:index>")
def player(uid: UID, index: int) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        return error_response(UIDUnknown(uid))

    try:
        episode = anime[index]
    except GrobberException as e:
        return error_response(e)

    return render_template("player.html", episode=episode, uid=uid, index=index)


@templates.route("/mal/episode/<UID:uid>")
def mal_episode_list(uid: UID) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        return error_response(UIDUnknown(uid))
    offset = cast_argument(request.args.get("offset"), int, 0)
    return render_template("mal/episode_list.html", episode_count=anime.episode_count, offset=offset)


@templates.route("/mal/episode/<UID:uid>/<int:index>")
def mal_episode(uid: UID, index: int) -> Response:
    anime = sources.get_anime(uid)
    if not anime:
        return error_response(UIDUnknown(uid))

    try:
        episode = anime[index]
    except GrobberException as e:
        return error_response(e)

    return render_template("mal/episode.html", episode=episode, uid=uid, index=index, episode_count=anime.episode_count)


@templates.route("/mal/settings")
def mal_settings():
    # MultiDicts have Lists for values (because there can be multiple values for the same key but we don't want that, thus the "to_dict"
    context = request.args.to_dict()
    return render_template("mal/settings.html", **context)
