__all__ = ["anext", "alist"]

from typing import Any, AsyncIterator, List, TypeVar

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
