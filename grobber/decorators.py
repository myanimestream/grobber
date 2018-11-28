import asyncio
from functools import wraps
from typing import Awaitable, Callable

_DEFAULT = object()


def cached_property(func: Callable[..., Awaitable]) -> property:
    cache_name = f"_{func.__name__}"
    lock_name = f"{cache_name}__lock"

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            lock = getattr(self, lock_name)
        except AttributeError:
            lock = asyncio.Lock()
            setattr(self, lock_name, lock)

        async with lock:
            val = getattr(self, cache_name, _DEFAULT)

            if val is _DEFAULT:
                val = await func(self, *args, **kwargs)

                setattr(self, cache_name, val)
                if func.__name__ in self.ATTRS:
                    self._dirty = True

        return val

    return property(wrapper)
