import asyncio
import logging
from itertools import chain
from typing import Any, Awaitable, Dict, Iterable, List, Optional

from grobber.anime import Anime, Episode, EpisodeNotFound, SourceAnime, Stream, sources
from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.locals import anime_collection
from grobber.uid import MediaType, UID
from grobber.utils import AIterable, afilter, aiter, amap, do_later, get_first

log = logging.getLogger(__name__)


class HasAnimesMixin:
    animes: Awaitable[List[SourceAnime]]

    def __repr__(self) -> str:
        if isinstance(self.animes, asyncio.Future):
            if self.animes.done():
                animes = self.animes.result()
                animes_str = ", ".join(repr(anime) for anime in animes)
                return f"{type(self).__name__} ({animes_str})"

        return super().__repr__()

    async def wait_for_all(self, fs: Iterable[Awaitable]) -> List[Any]:
        async def save_wait(future: Awaitable) -> Optional[Any]:
            try:
                return await future
            except Exception as e:
                log.warning(f"{self} couldn't await {future}: {e}")
                return None

        return list(filter(None, await asyncio.gather(*map(save_wait, fs))))

    async def get_from_all(self, attr: str, containers: Any = None) -> List[Any]:
        if containers is None:
            containers = await self.animes

        async def save_getattr(inst: Any, key: str) -> Optional[Any]:
            try:
                return await getattr(inst, key)
            except Exception as e:
                log.warning(f"{self} couldn't get {key} from {inst}: {e}")
                return None

        return list(filter(None, await asyncio.gather(*(save_getattr(container, attr) for container in containers))))

    async def get_from_first(self, attr: str, containers: Any = None) -> Any:
        if containers is None:
            containers = await self.animes

        return await get_first(getattr(container, attr) for container in containers)

    @cached_property
    async def episode_count(self) -> int:
        episode_counts = await self.get_from_all("episode_count")
        if not episode_counts:
            return 0

        return max(episode_counts)


class EpisodeGroup(HasAnimesMixin, Episode):
    index: int

    def __init__(self, animes: Awaitable[List[SourceAnime]], index: int):
        self.animes = animes
        self.index = index

    @cached_property
    async def episodes(self) -> List[Episode]:
        animes = await self.animes
        episodes = await self.wait_for_all(anime.get(self.index) for anime in animes)
        if not episodes:
            episode_count = await self.episode_count
            if self.index >= episode_count:
                raise EpisodeNotFound(self.index, episode_count)

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

        return list(filter(None, await self.wait_for_all([stream.working_external_self for stream in chain.from_iterable(streams)])))


class AnimeGroup(HasAnimesMixin, Anime):
    uids: List[UID]
    _title: str
    _language: Language
    _is_dub: bool

    def __init__(self, uids: List[UID], title: str, language: Language, is_dub: bool):
        self.uids = uids
        self._title = title
        self._language = language
        self._is_dub = is_dub

    def __repr__(self) -> str:
        return f"Group {super().__repr__()} ({len(self.uids)})"

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

    async def get(self, index: int) -> EpisodeGroup:
        return EpisodeGroup(asyncio.ensure_future(self.animes), index)

    @property
    async def uid(self) -> UID:
        return UID.create(MediaType.ANIME, UID.create_media_id(self._title), None, self._language, self._is_dub)

    @cached_property
    async def thumbnail(self) -> str:
        return await self.get_from_first("thumbnail")

    async def add_anime(self, anime: SourceAnime) -> None:
        uid = await anime.uid
        self.uids.append(uid)

        animes = await self.animes
        animes.append(anime)

    async def could_contain(self, anime: SourceAnime) -> bool:
        do_later(anime.preload_attrs("language", "is_dub", "title", "episode_count"))

        if self._language != await anime.language:
            return False

        if self._is_dub != await anime.is_dub:
            return False

        if self._title != await anime.title:
            return False

        episode_counts = await self.get_from_all("episode_count")

        real_max_ep_count = max(episode_counts)
        real_min_ep_count = min(episode_counts)

        # make sure that the difference between max and min is at least 4
        max_ep_count = max(real_max_ep_count, real_min_ep_count + 2)
        min_ep_count = min(real_min_ep_count, real_max_ep_count - 2)

        if not (min_ep_count <= await anime.episode_count <= max_ep_count):
            return False

        return True


async def group_animes(animes: AIterable, *, unique_groups: bool = True) -> List[AnimeGroup]:
    groups: List[AnimeGroup] = []
    async for anime in aiter(animes):
        for group in groups:
            if await group.could_contain(anime):
                await group.add_anime(anime)

                if unique_groups:
                    break
        else:
            auid, title, language, is_dub = await asyncio.gather(anime.uid, anime.title, anime.language, anime.is_dub)
            group = AnimeGroup([auid], title, language, is_dub)
            group.animes = [anime]
            groups.append(group)

    return groups


async def _get_anime_group(selector: Dict[str, Any]) -> Optional[AnimeGroup]:
    async def build_anime(doc: Dict[str, Any]) -> Optional[Anime]:
        try:
            return await sources.build_anime_from_doc(doc["_id"], doc)
        except Exception as e:
            title = doc.get("title") or doc.get("media_id") or "unknown"
            log.info(f"ignoring {title}: {e}")
            return None

    cursor = anime_collection.find(selector)
    anime_iter = afilter(None, amap(build_anime, cursor))
    groups = await group_animes(anime_iter, unique_groups=False)
    return max(groups, key=lambda group: len(group.uids))


async def get_anime_group(uid: UID) -> Optional[AnimeGroup]:
    return await _get_anime_group({
        "media_id": uid.media_id,
        f"language{SourceAnime._SPECIAL_MARKER}": uid.language.value,
        "is_dub": uid.dubbed
    })


async def get_anime_group_by_title(title: str, language: Language, dubbed: bool) -> Optional[AnimeGroup]:
    return await _get_anime_group({
        "title": title,
        f"language{SourceAnime._SPECIAL_MARKER}": language.value,
        "is_dub": dubbed
    })
