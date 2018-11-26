import re
from typing import Pattern, Union

from quart import Blueprint, Quart, Response, redirect, request

from ..url_pool import UrlPool, gogoanime_pool, nineanime_pool

forward = Blueprint("forward", __name__, url_prefix="/forward")

RE_ROUTE_CLEANER: Pattern = re.compile(r"\W+")


def create_forward(app: Union[Blueprint, Quart], pool: UrlPool, rule: str, path: str, *, include_query: bool = True) -> None:
    async def forwarder(**kwargs) -> Response:
        url = f"{path}"
        for name, arg in kwargs.items():
            url += f"/{arg}"
        if include_query:
            url += "?" + request.query_string.decode("utf-8")

        return redirect(await pool.url + url)

    forwarder.__name__ = pool.name + RE_ROUTE_CLEANER.sub("", path)

    app.route(rule)(forwarder)


gogoanime_map = {
    "/gogoanime/<path:url>": "/",
    "/gogoanime/search": "//search.html",
    "/gogoanime/episodes": "//load-list-episode"
}

for route, target in gogoanime_map.items():
    create_forward(forward, gogoanime_pool, route, target)

nineanime_map = {
    "/9anime/<path:url>": "/",
    "/9anime/search": "/search",
    "/9anime/watch/<path:url>": "/watch",
    "/9anime/ajax/film/servers/<path:url>": "/ajax/film/servers"
}

for route, target in nineanime_map.items():
    create_forward(forward, nineanime_pool, route, target)
