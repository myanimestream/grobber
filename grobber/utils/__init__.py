import ast
import asyncio
import json
import logging
import re
from difflib import SequenceMatcher
from string import Formatter
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Match, Optional, Tuple, TypeVar, Union

from quart import url_for

from . import aitertools
from .aitertools import *
from .async_string_formatter import AsyncFormatter
from .response import *

__all__ = ["AsyncFormatter",
           "create_response", "error_response",
           "add_http_scheme", "parse_js_json", "external_url_for", "format_available", "do_later",
           *aitertools.__all__,
           "fuzzy_bool", "get_certainty"]

log = logging.getLogger(__name__)

T2 = TypeVar("T2")
_DEFAULT = object()


def add_http_scheme(link: str, base_url: str = None, *, _scheme="http") -> str:
    if link.startswith("//"):
        return f"{_scheme}:{link}"
    elif not link.startswith(("http://", "https://")):
        if base_url:
            return base_url.rstrip("/") + "/" + link
        return f"{_scheme}://{link}"
    return link


def fuzzy_bool(s: Optional[str], *, default: bool = False) -> bool:
    if s is None:
        return default

    if s:
        return str(s).lower() in {"true", "t", "yes", "y", "1"}

    return False


def get_certainty(a: str, b: str) -> float:
    return round(SequenceMatcher(a=a, b=b).ratio(), 2)


def perform_safe(func: Callable, *args, **kwargs) -> Tuple[Optional[Exception], Optional[Any]]:
    try:
        return None, func(*args, **kwargs)
    except Exception as e:
        return e, None


RE_JSON_EXPANDER = re.compile(r"([`'])?([a-z0-9A-Z_]+)([`'])?\s*:(?=\s*[\[\d`'\"{])", re.DOTALL)
RE_JSON_REMOVE_TRAILING_COMMA = re.compile(r"([\]}])\s*,(?=\s*[\]}])")

RE_JSON_VARIABLE_DETECT = re.compile(r"\"(?P<key>[^\"]+?)\"\s*:\s*(?P<value>[^`'\"][a-zA-Z]+)\b,?")


def parse_js_json(text: str, *, variables: Mapping[str, Any] = None) -> Any:
    def _try_load(_text) -> Tuple[Optional[Exception], Any]:
        _exc = _data = None

        _exc, _data = perform_safe(json.loads, _text)
        if _exc is None:
            return None, _data

        _e, _data = perform_safe(ast.literal_eval, _text)
        if _e is None:
            return None, _data

        _e.__cause__ = _exc
        return _e, None

    valid_json = RE_JSON_EXPANDER.sub("\"\\2\": ", text).replace("'", "\"")
    valid_json = RE_JSON_REMOVE_TRAILING_COMMA.sub(r"\1", valid_json)

    e, data = _try_load(valid_json)
    if e is None:
        return data

    log.debug(f"failed to load js json data: {e}")

    _valid_names = {"true", "false", "null", "NaN", "Infinity", "-Infinity"}

    def _replacer(_match: Match) -> str:
        value = _match["value"]
        if value not in _valid_names:
            if variables:
                return json.dumps(variables.get(value))
            else:
                return "null"

        return _match[0]

    log.debug("trying again with invalid values removed.")
    valid_json = RE_JSON_VARIABLE_DETECT.sub(_replacer, valid_json)

    e, data = _try_load(valid_json)
    if e is None:
        return data

    raise e


def external_url_for(endpoint: str, **kwargs):
    kwargs["_external"] = True
    kwargs["_scheme"] = "https"
    return url_for(endpoint, **kwargs)


class _ModestFormatter(Formatter):
    def get_value(self, key: Union[str, int], args: List[Any], kwargs: Dict[Any, Any]) -> Any:
        try:
            return super().get_value(key, args, kwargs)
        except (IndexError, KeyError):
            return f"{{{key}}}"


ModestFormatter = _ModestFormatter()


def format_available(text: str, *args, **kwargs) -> str:
    return ModestFormatter.format(text, *args, **kwargs)


def do_later(target: Awaitable) -> None:
    async def safe_run(aw: Awaitable) -> None:
        try:
            await aw
        except Exception:
            log.exception(f"Something went wrong while awaiting {target}")

    asyncio.ensure_future(safe_run(target))
