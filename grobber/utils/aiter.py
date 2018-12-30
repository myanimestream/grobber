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


async def get_first(coros: Iterable[Awaitable[T]], predicate: Callable[[T], Union[bool, Awaitable[bool]]] = bool) -> Optional[T]:
    while coros:
        done, coros = await asyncio.wait(coros, return_when=asyncio.FIRST_COMPLETED)
        if done:
            result = next(iter(done)).result()
            res = predicate(result)
            if inspect.isawaitable(res):
                res = await res
            if res:
                for coro in coros:
                    coro.cancel()

                return result

    return None
