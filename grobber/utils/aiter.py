__all__ = ["anext", "alist", "get_first"]

import asyncio
import inspect
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, List, Optional, TypeVar, Union

_DEFAULT = object()

T = TypeVar("T")


async def anext(iterable: AsyncIterator[T], default: Any = _DEFAULT) -> T:
    try:
        return await iterable.__anext__()
    except StopAsyncIteration:
        if default is _DEFAULT:
            raise
        else:
            return default


async def alist(iterable: AsyncIterator[T]) -> List[T]:
    items = []

    async for item in iterable:
        items.append(item)

    return items


async def get_first(coros: Iterable[Awaitable[T]],
                    predicate: Callable[[T], Union[bool, Awaitable[bool]]] = bool, *,
                    cancel_running: bool = True) -> Optional[T]:
    """Return the result of the first coroutine from coros that finishes with a result that passes predicate.

    :param coros: coroutines to wait for
    :param predicate: predicate to check for a positive result (defaults to a truthy check)
    :param cancel_running:  Whether or not to cancel coroutines that are still running
    :return: first result or None
    """
    while coros:
        done, coros = await asyncio.wait(coros, return_when=asyncio.FIRST_COMPLETED)
        if done:
            result = next(iter(done)).result()
            res = predicate(result)
            if inspect.isawaitable(res):
                res = await res

            if not res:
                continue

            if cancel_running:
                for coro in coros:
                    coro.cancel()

            return result

    return None
