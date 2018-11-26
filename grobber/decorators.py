from functools import wraps
from typing import Awaitable, Callable

_DEFAULT = object()


def cached_property(func: Callable[..., Awaitable]) -> property:
    cache_name = "_" + func.__name__

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        val = getattr(self, cache_name, _DEFAULT)
        if val is _DEFAULT:
            val = await func(self, *args, **kwargs)
            setattr(self, cache_name, val)
            if func.__name__ in self.ATTRS:
                self._dirty = True

        return val

    return property(wrapper)
