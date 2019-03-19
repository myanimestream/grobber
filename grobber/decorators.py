import asyncio
import logging
from contextlib import _AsyncGeneratorContextManager
from functools import wraps
from typing import AsyncGenerator, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .stateful import Stateful

log = logging.getLogger(__name__)

_DEFAULT = object()


def retry_with_proxy(*exceptions: Exception, attempts: int = 5):
    """
    When the underlying method of a :class:`grobber.stateful.Stateful` object
    throws an exceptions that is a subtype of ``exceptions`` it reloads the
    :class:`grobber.request.Request` and re-runs the method until it either succeeds,
    or the amount of retries exceeds ``attempts``.

    Example:

    When calling the ``Key.get_key`` method it will re-run when it raises a `KeyError`.

    .. code-block:: python
        :emphasize-lines: 2

        class Key(Stateful):
            @retry_with_proxy(KeyError)
            async def get_key():
                data = await self._req.json
                return data["key"]

    :return: Decorator which applies the retry logic to the decorated method.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self: "Stateful", *args, **kwargs):
            last_exception = None

            for attempt in range(attempts):
                try:
                    return await func(self, *args, **kwargs)
                except exceptions as e:
                    if last_exception:
                        e.__origin__ = last_exception

                    last_exception = e
                    request = self._req
                    request._use_proxy = True
                    request.reset()
                    log.info(f"{func.__qualname__} failed, trying again with proxy {attempt + 1}/{attempts}")

            if last_exception:
                raise last_exception
            else:
                raise ValueError("There wasn't even an attempt lel")

        return wrapper

    return decorator


def cached_property(func: Callable[..., Awaitable]):
    cache_name = f"_{func.__name__}"
    lock_name = f"{cache_name}__lock"

    def get_lock(self) -> asyncio.Lock:
        try:
            lock = getattr(self, lock_name)
        except AttributeError:
            lock = asyncio.Lock()
            setattr(self, lock_name, lock)

        return lock

    @wraps(func)
    async def getter(self, *args, **kwargs):
        lock = get_lock(self)

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

    def setter(self, value):
        lock = get_lock(self)
        if lock.locked():
            log.warning(f"Lock {lock_name} already acquired for {func}")

        setattr(self, cache_name, value)

        try:
            func.__name__ in self.ATTRS
        except AttributeError:
            pass
        else:
            self._dirty = True

    def deleter(self):
        lock = get_lock(self)
        if lock.locked():
            log.warning(f"Lock {lock_name} already acquired for {func}")

        delattr(self, cache_name)

        try:
            func.__name__ in self.ATTRS
        except AttributeError:
            pass
        else:
            self._dirty = True

    return property(getter, setter, deleter)


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
        return await self.gen.__anext__()


def cached_contextmanager(func: Callable[..., AsyncGenerator]) -> property:
    ref_name = f"_{func.__name__}_ref"

    @wraps(func)
    def wrapper(self):
        try:
            ref = getattr(self, ref_name)
        except AttributeError:
            ref = _RefCounter(func, self)
            setattr(self, ref_name, ref)

        return ref

    return property(wrapper)
