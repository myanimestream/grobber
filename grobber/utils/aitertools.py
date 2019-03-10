__all__ = ["AIterable", "AFunction", "aiter", "anext", "alist", "maybe_await", "amap", "afilter", "get_first"]

import asyncio
import inspect
from typing import Any, AsyncIterable, AsyncIterator, Awaitable, Callable, Container, Iterable, List, Optional, Set, Tuple, Type, TypeVar, Union, \
    overload

_DEFAULT = object()

T = TypeVar("T")
R = TypeVar("R")

AIterable = Union[Iterable[T], AsyncIterable[T]]
AFunction = Union[Callable[[T], R], Callable[[T], Awaitable[R]]]


def aiter(iterable: AIterable[T]) -> AsyncIterator[T]:
    """Convert any kind of iterable to an async iterable"""
    if isinstance(iterable, AsyncIterator):
        return iterable
    elif isinstance(iterable, AsyncIterable):
        return iterable.__aiter__()
    elif isinstance(iterable, Iterable):
        async def gen() -> AsyncIterator[T]:
            for item in iterable:
                yield item

        return gen()
    else:
        raise TypeError(f"Type {type(iterable)} is not aiterable.")


async def anext(iterable: AIterable[T], default: Any = _DEFAULT) -> T:
    try:
        if isinstance(iterable, AsyncIterator):
            return await iterable.__anext__()
        else:
            return next(iterable)
    except (StopAsyncIteration, StopIteration):
        if default is _DEFAULT:
            raise
        else:
            return default


@overload
async def alist(iterable: AIterable[T], constructor: tuple) -> Tuple[T]: ...


@overload
async def alist(iterable: AIterable[T], constructor: list) -> List[T]: ...


@overload
async def alist(iterable: AIterable[T]) -> List[T]: ...


@overload
async def alist(iterable: AIterable[T], constructor: set) -> Set[T]: ...


async def alist(iterable: AIterable[T], constructor: Type[Container] = list) -> Container[T]:
    # noinspection PyArgumentList
    return constructor([item async for item in aiter(iterable)])


async def maybe_await(obj: Union[Awaitable[T], T]) -> T:
    if inspect.isawaitable(obj):
        return await obj
    else:
        return obj


async def amap(func: AFunction, iterable: AIterable[T]) -> AsyncIterator[R]:
    async for item in aiter(iterable):
        yield await maybe_await(func(item))


async def afilter(func: Optional[AFunction], iterable: AIterable[T]) -> AsyncIterator[T]:
    async for item in aiter(iterable):
        if func is None:
            if item:
                yield item
        elif await maybe_await(func(item)):
            yield item


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
        done, coros = await asyncio.wait(list(coros), return_when=asyncio.FIRST_COMPLETED)
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
