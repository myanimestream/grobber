import abc
import asyncio
import inspect
import logging
from collections import deque
from contextlib import suppress
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Pattern, TypeVar

import bson

from .request import Request

log = logging.getLogger(__name__)

_DEFAULT = object()
VALID_BSON_TYPES = (dict, list, tuple, bson.ObjectId, datetime, Pattern, str, int, float, bool, bytes, type(None))
# noinspection PyTypeHints
BsonType = TypeVar("BsonType", *VALID_BSON_TYPES)


def check_container_bson(data: Any) -> bool:
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(key, str):
                return False
            if not check_container_bson(value):
                return False
    elif isinstance(data, (list, tuple)):
        for item in data:
            if not check_container_bson(item):
                return False
    else:
        if not isinstance(data, VALID_BSON_TYPES):
            return False
    return True


class Stateful(abc.ABC):
    __SPECIAL_MARKER = "$state"
    INCLUDE_CLS = False
    ATTRS = ()

    _req: Request
    _dirty: bool

    def __init__(self, req):
        self._req = req

        self.ATTRS = set(attr for base in type(self).__mro__ for attr in getattr(base, "ATTRS", []))
        self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    @dirty.setter
    def dirty(self, value: bool):
        self._dirty = value

    @property
    def qualcls(self) -> str:
        return f"{type(self).__module__}.{type(self).__qualname__}"

    def serialise_special(self, key: str, value: Any) -> BsonType:
        raise TypeError(f"Special key \"{key}\" with value {value} doesn't have a handler to serialise!")

    @classmethod
    def deserialise_special(cls, key: str, value: BsonType) -> Any:
        raise TypeError(f"Special key \"{key}\" doesn't have a handler to deserialise!")

    async def preload_attrs(self, *attrs: str, recursive: bool = False) -> List[Any]:
        if not attrs:
            attrs = self.ATTRS

        async def preload(attr: str) -> Any:
            value = getattr(self, attr)

            if inspect.isawaitable(value):
                value = await value

            if recursive:
                stack = deque()
                stack.append(value)

                while stack:
                    v = stack.pop()

                    if isinstance(v, Stateful):
                        await v.preload_attrs(recursive=recursive)
                    elif isinstance(v, Mapping):
                        stack.extend(v.keys())
                        stack.extend(v.values())
                    elif isinstance(v, Iterable) and not isinstance(v, str):
                        stack.extend(v)

            return value

        return await asyncio.gather(*(preload(attr) for attr in attrs))

    @property
    def state(self) -> Dict[str, BsonType]:
        data = {"req": self._req.state}
        if self.INCLUDE_CLS:
            data["cls"] = self.qualcls
        for attr in self.ATTRS:
            val = getattr(self, "_" + attr, _DEFAULT)
            if val is not _DEFAULT:
                if not check_container_bson(val):
                    val = self.serialise_special(attr, val)
                    attr += self.__SPECIAL_MARKER
                data[attr] = val
        return data

    @classmethod
    def from_state(cls, state: Dict[str, BsonType]) -> "Stateful":
        inst = cls(Request.from_state(state.pop("req")))
        for key, value in state.items():
            if key.endswith(cls.__SPECIAL_MARKER):
                key = key[:-len(cls.__SPECIAL_MARKER)]
                value = cls.deserialise_special(key, value)
            setattr(inst, "_" + key, value)
        return inst


class Expiring(Stateful):
    MINUTE = 60
    HOUR = MINUTE * 60
    DAY = HOUR * 24

    CHANGING_ATTRS = ()
    EXPIRE_TIME = HOUR

    ATTRS = ("last_update",)
    _last_update: datetime

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.CHANGING_ATTRS = set(attr for base in type(self).__mro__ for attr in getattr(base, "CHANGING_ATTRS", []))
        self._last_update = datetime.now()

    def __getattribute__(self, name: str) -> Any:
        if name in type(self).CHANGING_ATTRS:
            if self._update:
                log.debug(f"{self}: time for an update")
                for attr in type(self).CHANGING_ATTRS:
                    with suppress(AttributeError):
                        delattr(self, f"_{attr}")
        return super().__getattribute__(name)

    @property
    def last_update(self) -> datetime:
        return self._last_update

    @property
    def _update(self) -> bool:
        current_time = datetime.now()
        last_time = self._last_update
        if (current_time - last_time).total_seconds() > self.EXPIRE_TIME:
            self._last_update = current_time
            return True
        return False
