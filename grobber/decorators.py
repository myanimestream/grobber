import asyncio
from contextlib import _AsyncGeneratorContextManager
from functools import wraps
from typing import AsyncGenerator, Awaitable, Callable

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

                try:
                    func.__name__ in self.ATTRS
                except AttributeError:
                    pass
                else:
                    self._dirty = True

        return val

    return property(wrapper)


class _RefCounter(_AsyncGeneratorContextManager):
    def __init__(self, func, *args, **kwargs):
        super().__init__(func, args, kwargs)
        self.ref_count = 1

    async def __aenter__(self):
        self.ref_count += 1
        return await self.value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.ref_count -= 1

        if self.ref_count <= 0:
            await super().__aexit__(exc_type, exc_val, exc_tb)

    @cached_property
    async def value(self):
        return await super().__aenter__()


def cached_contextmanager(func: Callable[..., AsyncGenerator]) -> property:
    ref_name = f"_{func.__name__}_ref"

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            ref = getattr(self, ref_name)
        except AttributeError:
            ref = _RefCounter(func, self, *args, **kwargs)
            setattr(self, ref_name, ref)

        return ref

    return property(wrapper)
