import asyncio
import logging
import time
from enum import IntEnum
from itertools import chain
from typing import Any, Awaitable, Callable, Dict, Iterable, Iterator, List, Optional, Tuple, TypeVar, cast

from grobber import index_scraper
from grobber.anime import Anime, Episode, EpisodeNotFound, SourceAnime, Stream, sources
from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.locals import anime_collection, source_index_collection
from grobber.uid import MediumType, UID
from grobber.utils import AIterable, afilter, aiter, amap, do_later, get_first

log = logging.getLogger(__name__)

T = TypeVar("T")


async def smart_wait(fs: Iterable[Awaitable[T]], *,
                     result_selector: Callable[[T], bool] = None,
                     timeout: float = None) -> List[T]:
    """Wait for at least one future to complete.

    Wait for the first future to complete and then give the other futures
    half the time it took for the first future.

    Args:
        fs: Iterable of futures to wait for
        result_selector: Selector which selects which values are to be accepted.
            Invalid values will not be returned or count toward the first result.
        timeout: Time to wait for the first result

    Returns:
        List of results of the futures that completed in time.
    """
    results: List[T] = []

    completed_iter: Iterator[Awaitable[T]] = asyncio.as_completed(fs, timeout=timeout)
    while True:
        start = time.perf_counter()
        try:
            first_result = await next(completed_iter)
        except StopIteration:
            return []

        first_time = time.perf_counter() - start

        if result_selector and not result_selector(first_result):
            continue

        results.append(first_result)
        break

    pending_fs = list(completed_iter)
    if not pending_fs:
        return results

    done_fs, _ = await asyncio.wait(pending_fs, timeout=first_time / 2)

    for future in done_fs:
        result = future.result()

        if result_selector and not result_selector(first_result):
            continue

        results.append(result)

    return results


class WaitStrategy(IntEnum):
    ALL = 0
    SMART = 1


class HasAnimesMixin:
    animes: Awaitable[List[SourceAnime]]

    def __repr__(self) -> str:
        if isinstance(self.animes, asyncio.Future):
            if self.animes.done():
                animes = self.animes.result()
                animes_str = ", ".join(repr(anime) for anime in animes)
                return f"{type(self).__name__} ({animes_str})"

        return super().__repr__()

    async def wait_for_all(self, fs: Iterable[Awaitable], *,
                           timeout: float = None,
                           strategy=WaitStrategy.SMART) -> List[Any]:
        async def save_wait(future: Awaitable) -> Optional[Any]:
            try:
                return await asyncio.wait_for(future, timeout=timeout)
            except TimeoutError:
                log.debug(f"{future!r} timed-out!")
            except Exception as e:
                log.warning(f"{self!r} couldn't await {future!r}: {e}")

            return None

        fs = map(save_wait, fs)

        if strategy == WaitStrategy.SMART:
            return await smart_wait(fs, result_selector=lambda result: result is not None, timeout=timeout)
        elif strategy == WaitStrategy.ALL:
            return list(filter(None, await asyncio.gather(*fs)))
        else:
            raise TypeError("Invalid wait strategy")

    async def get_from_all(self, attr: str, containers: Any = None, *,
                           timeout: float = None,
                           strategy=WaitStrategy.SMART) -> List[Any]:
        if containers is None:
            containers = await self.animes

        async def save_getattr(inst: Any, key: str) -> Optional[Any]:
            try:
                return await getattr(inst, key)
            except Exception as e:
                log.warning(f"{self!r} couldn't get {key} from {inst!r}: {e!r}")
                return None

        log.debug(f"getting {attr} from all {len(containers)} containers")
        return await self.wait_for_all((save_getattr(container, attr) for container in containers),
                                       timeout=timeout,
                                       strategy=strategy)

    async def get_from_first(self, attr: str, containers: Any = None) -> Any:
        if containers is None:
            containers = await self.animes

        return await get_first(getattr(container, attr) for container in containers)


class EpisodeGroup(HasAnimesMixin, Episode):
    index: int

    def __init__(self, animes: Awaitable[List[SourceAnime]], index: int):
        self.animes = animes
        self.index = index

    @cached_property
    async def episodes(self) -> List[Episode]:
        animes = await self.animes
        episodes = await self.wait_for_all((anime.get(self.index) for anime in animes), timeout=15)
        return episodes

    @cached_property
    async def raw_streams(self) -> List[str]:
        episodes = await self.episodes
        all_raw_streams = await self.get_from_all("raw_streams", episodes)
        return list(chain.from_iterable(all_raw_streams))

    @cached_property
    async def working_streams(self) -> List[Stream]:
        episodes = await self.episodes
        streams = await self.get_from_all("streams", episodes)

        return list(filter(None, await self.wait_for_all(
            [stream.working_external_self for stream in chain.from_iterable(streams)])))

    @property
    def state(self) -> Dict[str, Any]:
        try:
            # noinspection PyUnresolvedReferences
            episode_list: List[SourceEpisode] = self._episodes
        except AttributeError:
            episodes = []
        else:
            episodes = [episode.state for episode in episode_list]

        return {
            "index": self.index,
            "episodes": episodes,
        }


class AnimeGroup(HasAnimesMixin, Anime):
    uids: List[UID]
    _title: str
    _language: Language
    _is_dub: bool

    def __init__(self, uids: List[UID], title: str, language: Language, is_dub: bool, *,
                 animes: List[SourceAnime] = None):
        self.uids = uids
        self._title = title
        self._language = language
        self._is_dub = is_dub

        if animes:
            # noinspection PyPropertyAccess
            self.animes = animes

    def __repr__(self) -> str:
        return f"Group {super().__repr__()} ({len(self.uids)})"

    @property
    def source_count(self) -> int:
        return len(self.uids)

    @property
    async def title(self) -> str:
        return self._title

    @property
    async def language(self) -> Language:
        return self._language

    @property
    async def is_dub(self) -> bool:
        return self._is_dub

    @cached_property
    async def animes(self) -> List[SourceAnime]:
        return list((await sources.get_animes(self.uids)).values())

    @cached_property
    async def episode_count(self) -> int:
        episode_counts = await self.get_from_all("episode_count")
        if not episode_counts:
            return 0

        return max(episode_counts)

    async def get(self, index: int) -> EpisodeGroup:
        episode_count = await self.episode_count

        if index >= episode_count:
            raise EpisodeNotFound(index, episode_count)

        return EpisodeGroup(asyncio.ensure_future(self.animes), index)

    @property
    async def uid(self) -> UID:
        return UID.create(MediumType.ANIME, UID.create_medium_id(self._title), None, self._language, self._is_dub)

    @cached_property
    async def thumbnail(self) -> str:
        return await self.get_from_first("thumbnail")

    @property
    def state(self) -> Dict[str, Any]:
        try:
            # noinspection PyUnresolvedReferences
            anime_list: List[SourceAnime] = self._animes
        except AttributeError:
            animes = {}
        else:
            animes = {getattr(anime, "_id", None): anime.state for anime in anime_list}

        return {
            "title": self._title,
            "language": self._language.value,
            "dubbed": self._is_dub,
            "animes": {uid: animes.get(uid) for uid in self.uids},
        }

    async def add_anime(self, anime: SourceAnime) -> None:
        uid = await anime.uid
        if uid in self.uids:
            return

        self.uids.append(uid)

        try:
            # noinspection PyUnresolvedReferences
            animes: List[SourceAnime] = self._animes
        except AttributeError:
            pass
        else:
            animes.append(anime)

    async def add_animes(self, animes: AIterable[SourceAnime]) -> None:
        await asyncio.gather(*map(self.add_anime, animes))

    async def could_contain(self, anime: SourceAnime) -> bool:
        do_later(anime.preload_attrs("language", "is_dub", "media_id", "episode_count"))

        if self._language != await anime.language:
            return False

        if self._is_dub != await anime.is_dub:
            return False

        if await self.media_id != await anime.media_id:
            return False

        episode_counts: List[int] = await self.get_from_all("episode_count")
        # ignore if there are no episode counts
        if episode_counts:
            real_max_ep_count = max(episode_counts)
            real_min_ep_count = min(episode_counts)

            # make sure that the difference between max and min is at least 4
            max_ep_count = max(real_max_ep_count, real_min_ep_count + 2)
            min_ep_count = min(real_min_ep_count, real_max_ep_count - 2)

            try:
                episode_count = await anime.episode_count
            except Exception:
                log.exception(f"Couldn't get episode count from {anime!r}")
                return False

            if not isinstance(episode_count, int):
                log.error(
                    f"{self} not accepting: {anime!r}, returned something other than an int for episode_count: {episode_count}")
                return False

            if not (min_ep_count <= episode_count <= max_ep_count):
                return False

        return True


async def group_animes(animes: AIterable, *, unique_groups: bool = True) -> List[AnimeGroup]:
    preload_queue = asyncio.Queue()

    async def preload_worker():
        async for anime in aiter(animes):
            anime = cast(SourceAnime, anime)
            await anime.preload_attrs()
            preload_queue.put_nowait(anime)

    groups: List[AnimeGroup] = []

    async def group_worker():
        while True:
            anime = await preload_queue.get()

            found_group = False

            for group in groups:
                if await group.could_contain(anime):
                    await group.add_anime(anime)
                    found_group = True

                    if unique_groups:
                        break

            if not found_group:
                auid, title, language, is_dub = await asyncio.gather(anime.uid, anime.title, anime.language,
                                                                     anime.is_dub)
                group = AnimeGroup([auid], title, language, is_dub, animes=[anime])
                groups.append(group)

            preload_queue.task_done()

    group_future = asyncio.ensure_future(group_worker())
    await preload_worker()
    await preload_queue.join()

    group_future.cancel()

    return groups


async def _get_anime_group(selector: Dict[str, Any]) -> Optional[AnimeGroup]:
    async def build_anime(doc: Dict[str, Any]) -> Optional[Anime]:
        try:
            anime = await sources.build_anime_from_doc(doc["_id"], doc)
        except Exception as e:
            title = doc.get("title") or doc.get("media_id") or "unknown"
            log.info(f"ignoring {title}: {e!r}")
            return None

        return anime

    cursor = anime_collection.find(selector)
    anime_iter = afilter(None, amap(build_anime, cursor))
    groups = await group_animes(anime_iter, unique_groups=False)
    if not groups:
        return None
    log.info(f"got {len(groups)} group(s)")
    return max(groups, key=lambda group: len(group.uids))


async def get_anime_group(uid: UID) -> Optional[AnimeGroup]:
    anime_group, medium_group = cast(
        Tuple[Optional[AnimeGroup], Optional[index_scraper.MediumGroup]],
        await asyncio.gather(
            _get_anime_group({
                "media_id": uid.medium_id,
                f"language{SourceAnime._SPECIAL_MARKER}": uid.language.value,
                "is_dub": uid.dubbed
            }),
            index_scraper.get_medium_group_by_uid(source_index_collection, uid),
        ),
    )

    if anime_group is None:
        if medium_group is not None:
            return index_scraper.source_group_from_medium_group(medium_group)
        else:
            return None

    if medium_group is not None:
        medium_source_animes = index_scraper.source_animes_from_medium_group(medium_group)
        await anime_group.add_animes(medium_source_animes)

    return anime_group


async def get_anime_group_by_title(title: str, language: Language, dubbed: bool) -> Optional[AnimeGroup]:
    return await _get_anime_group({
        "title": title,
        f"language{SourceAnime._SPECIAL_MARKER}": language.value,
        "is_dub": dubbed
    })
