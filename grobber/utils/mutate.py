from collections import deque
from contextlib import suppress
from typing import Callable, Deque, MutableMapping, Optional, TypeVar

__all__ = ["mut_map_filter_items", "mut_map_filter_values"]

K = TypeVar("K")
V = TypeVar("V")

MutMapType = MutableMapping[K, V]

MMT = TypeVar("MMT", bound=MutableMapping)


def mut_map_filter_items(callback: Optional[Callable[[K, V], bool]], mapping: MutableMapping[K, V]) -> None:
    if callback is None:
        def callback(k: K, v: V) -> bool:
            return k is None or v is None

    keys_to_remove: Deque[str] = deque()

    for key, value in mapping.items():
        try:
            should_remove = callback(key, value)
        except Exception:
            should_remove = True

        if should_remove:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        with suppress(KeyError):
            del mapping[key]


def mut_map_filter_values(callback: Optional[Callable[[K, V], bool]], mapping: MutableMapping[K, V]) -> None:
    if callback is None:
        def item_callback(_, value: V) -> bool:
            return value is None
    else:
        def item_callback(_, value: V) -> bool:
            return callback(value)

    mut_map_filter_items(item_callback, mapping)
