__all__ = ["create_response", "error_response", "cast_argument", "add_http_scheme", "parse_js_json", "thread_pool", "wait_for_first",
           "ChangelogEntry", "Version", "external_url_for", "format_available"]

import concurrent.futures
import json
import logging
import re
from collections import namedtuple
from concurrent.futures import Executor, ThreadPoolExecutor
from string import Formatter
from typing import Any, Callable, Dict, Iterator, List, Optional, TypeVar, Union

from flask import Response, current_app, jsonify, request, url_for

from .exceptions import GrobberException

log = logging.getLogger(__name__)

T = TypeVar("T")
T2 = TypeVar("T2")
_DEFAULT = object()


def create_response(data: dict = None, success: bool = True, **kwargs) -> Response:
    data = data or {}
    data.update(kwargs)
    data["success"] = success
    return jsonify(data)


def error_response(exception: GrobberException) -> Response:
    data = {
        "msg": exception.msg,
        "code": exception.code,
        "name": type(exception).__name__
    }
    return create_response(data, success=False)


def cast_argument(val: T, cls: Callable[[T], T2], default: Any = _DEFAULT) -> T2:
    try:
        new_val = cls(val)
    except Exception as e:
        if default is _DEFAULT:
            raise e
        else:
            return default
    else:
        return new_val


def add_http_scheme(link: str, base_url: str = None, *, _scheme="http") -> str:
    if link.startswith("//"):
        return f"{_scheme}:{link}"
    elif not link.startswith(("http://", "https://")):
        if base_url:
            return base_url.rstrip("/") + "/" + link
        return f"{_scheme}://{link}"
    return link


RE_JSON_EXPANDER = re.compile(r"(['\"])?([a-z0-9A-Z_]+)(['\"])?(\s)?:(?=(\s)?[\[\d\"'{])", re.DOTALL)
RE_JSON_REMOVE_TRAILING_COMMA = re.compile(r"([\]}])\s*,(?=\s*[\]}])")


def parse_js_json(text: str):
    valid_json = RE_JSON_EXPANDER.sub("\"\\2\": ", text).replace("'", "\"")
    valid_json = RE_JSON_REMOVE_TRAILING_COMMA.sub(r"\1", valid_json)
    return json.loads(valid_json)


THREAD_WORKERS = 10
thread_pool: Executor = ThreadPoolExecutor(max_workers=THREAD_WORKERS)


def wait_for_first(items: List[Callable[..., T]], cond: Callable[[T], bool] = bool) -> Optional[T]:
    fs = [thread_pool.submit(item) for item in items]
    fut_iter = concurrent.futures.as_completed(fs)
    for fut in fut_iter:
        res = fut.result()
        if cond(res):
            for future in fs:
                future.cancel()
            return res


ChangelogEntry = namedtuple("ChangelogEntry", ("text", "priority", "version", "date"))


class Version:
    def __init__(self, major: int, minor: int, patch: int):
        self.major = major
        self.minor = minor
        self.patch = patch

    def __len__(self) -> int:
        return 3

    def __iter__(self) -> Iterator[int]:
        return iter((self.major, self.minor, self.patch))

    def __str__(self) -> str:
        return ".".join(str(i) for i in self)

    @classmethod
    def from_version_num(cls, version_num: int) -> "Version":
        version = [(version_num & (16 ** (4 * i) - 1)) >> ((i - 1) * 16) for i in range(3, 0, -1)]
        return cls(*version)

    @property
    def version_num(self) -> int:
        return sum(part << (len(self) - i) * 16 for i, part in enumerate(self, 1))


def external_url_for(endpoint, **kwargs):
    kwargs["_external"] = False
    kwargs["_scheme"] = None
    url = url_for(endpoint, **kwargs)

    if "HOST_URL" in current_app.config:
        return current_app.config["HOST_URL"] + url
    else:
        return request.host_url.rstrip("/") + url


class _ModestFormatter(Formatter):
    def get_value(self, key: Union[str, int], args: List[Any], kwargs: Dict[Any, Any]) -> Any:
        try:
            return super().get_value(key, args, kwargs)
        except (IndexError, KeyError):
            return f"{{{key}}}"


ModestFormatter = _ModestFormatter()


def format_available(text: str, *args, **kwargs) -> str:
    return ModestFormatter.format(text, *args, **kwargs)
