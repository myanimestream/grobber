import asyncio
import logging
import re
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional, Pattern, Tuple

import bs4
from yarl import URL

from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.request import DefaultUrlFormatter, Request
from grobber.url_pool import UrlPool
from grobber.utils import get_certainty, mut_map_filter_values
from . import register_source
from ..models import SearchResult, SourceAnime, SourceEpisode

__all__ = ["AnimeVibeEpisode", "extract_stack_info", "AnimeVibeAnime", "animevibe_pool"]

log = logging.getLogger(__name__)

RE_EXTRACT_EPISODES: Pattern = re.compile(r"(\d+) episode\(s\)", re.IGNORECASE)
RE_FIX_THUMBNAIL_URL: Pattern = re.compile(r"-\d+x\d+(?=\.\w{3}$)")


class AnimeVibeEpisode(SourceEpisode):
    @cached_property
    async def player_url(self) -> str:
        bs = await self._req.bs

        frame: Optional[bs4.Tag] = bs.select_one("#main_frame")
        if not frame:
            raise ValueError(f"{self} Couldn't find main frame on episode page {bs}")

        relative_url = frame["src"]
        return f"{{{animevibe_pool}}}{relative_url}"

    @cached_property
    async def player_req(self) -> Request:
        return Request(await self.player_url)

    @cached_property
    async def raw_streams(self) -> List[str]:
        bs = await (await self.player_req).bs
        source_options: List[bs4.Tag] = bs.select("#selectpicker option")

        streams: List[str] = []

        for source_option in source_options:
            try:
                raw_url = source_option["value"]
            except KeyError:
                log.info(f"{self} encountered source without url: {source_option}")
                continue

            try:
                url = URL(raw_url)
            except ValueError:
                log.info(f"{self} encountered invalid url: {raw_url}")
                continue

            raw_video_url = url.query.get("vid")
            if not raw_video_url:
                continue

            try:
                video_url = URL(raw_video_url)
            except ValueError:
                log.info(f"{self} encountered invalid video url: {raw_video_url}")
                continue

            if not video_url.host:
                continue

            if not video_url.scheme:
                video_url = video_url.with_scheme("http")

            streams.append(str(video_url))

        return streams


def maybe_trim_suffix(s: str, suffix: str) -> Tuple[str, bool]:
    if s.endswith(suffix):
        return s[:-len(suffix)], True
    else:
        return s, False


def parse_raw_title(raw_title: str) -> Tuple[str, bool]:
    return maybe_trim_suffix(raw_title, " (Dub)")


def fix_thumbnail_url(raw_thumbnail: str) -> str:
    return RE_FIX_THUMBNAIL_URL.sub("", raw_thumbnail, 1)


def extract_episode_count(text: str) -> Optional[int]:
    match = RE_EXTRACT_EPISODES.search(text)

    if not match:
        return None

    raw_eps = match.group(1)

    try:
        return int(raw_eps)
    except ValueError:
        return None


@dataclass()
class StackInfo:
    url: str
    title: str
    dubbed: bool
    thumbnail: Optional[str]
    episode_count: Optional[int]


def extract_stack_info(element: bs4.Tag) -> Optional[StackInfo]:
    title_container: Optional[bs4.Tag] = element.select_one(".item-details .entry-title a")
    if not title_container:
        log.warning(f"couldn't find title container in {element}")
        return None

    try:
        raw_url = title_container["href"]
    except KeyError:
        log.warning(f"couldn't get url from title container: {title_container}")
        return None

    try:
        relative_url = URL(raw_url)
    except ValueError:
        log.warning(f"couldn't interpret url: {raw_url}")
        return None
    else:
        url = f"{{{animevibe_pool}}}{relative_url.path}"

    raw_title = title_container.text
    title, is_dub = parse_raw_title(raw_title)

    thumbnail_container: Optional[bs4.Tag] = element.select_one("img.entry-thumb")
    if thumbnail_container:
        raw_thumbnail = thumbnail_container.get("src")
        thumbnail = fix_thumbnail_url(raw_thumbnail)
    else:
        thumbnail = None

    episode_container: Optional[bs4.Tag] = element.select_one(".td-excerpt")
    if episode_container:
        episode_count = extract_episode_count(episode_container.text)
    else:
        episode_count = None

    return StackInfo(url, title, is_dub, thumbnail, episode_count)


class AnimeVibeAnime(SourceAnime):
    ATTRS = ("slug",)
    EPISODE_CLS = AnimeVibeEpisode

    @classmethod
    async def search(cls, query: str, *,
                     dubbed: bool = False, language: Language = Language.ENGLISH) -> AsyncIterator[SearchResult]:
        if language != Language.ENGLISH:
            return

        req = Request(f"{{{animevibe_pool}}}/page/1", dict(s=query))
        bs = await req.bs

        results: List[bs4.Tag] = bs.select(".td-main-content .td-animation-stack")

        for result in results:
            info = extract_stack_info(result)
            if info is None or info.dubbed != dubbed:
                continue

            data = {
                "title": info.title,
                "is_dub": info.dubbed,
                "thumbnail": info.thumbnail,
                "episode_count": info.episode_count,
            }

            mut_map_filter_values(None, data)

            req = Request(info.url)
            anime = cls(req, data=data)

            yield SearchResult(anime, get_certainty(info.title, query))

    @cached_property
    async def slug(self) -> str:
        parts = URL(self._req.raw_finalised_url).parts
        # skip "/" and "a"
        return parts[2]

    @cached_property
    async def is_dub(self) -> bool:
        # noinspection PyPropertyAccess
        self.title, val = parse_raw_title(await self.get_raw_title())
        return val

    @cached_property
    async def language(self) -> Language:
        return Language.ENGLISH

    @cached_property
    async def title(self) -> str:
        # noinspection PyPropertyAccess
        val, self.is_dub = parse_raw_title(await self.get_raw_title())
        return val

    @cached_property
    async def thumbnail(self) -> Optional[str]:
        bs = await self._req.bs
        container: Optional[bs4.Tag] = bs.select_one("#animeinfo .modal-body img")
        if not container:
            return None

        return container.get("src")

    @cached_property
    async def episode_count(self) -> int:
        bs = await self._req.bs
        container: Optional[bs4.Tag] = bs.select_one("#animeinfo .modal-body")

        if not container:
            return await super().episode_count

        ep_container: Optional[bs4.NavigableString] = container.find_next(string=RE_EXTRACT_EPISODES)
        if not ep_container:
            return await super().episode_count

        raw_ep_text = str(ep_container)
        episode_count = extract_episode_count(raw_ep_text)

        if episode_count is not None:
            return episode_count
        else:
            log.error(f"{self} Couldn't parse episode count from {raw_ep_text!r}")
            return await super().episode_count

    async def get_raw_title(self) -> str:
        bs = await self._req.bs

        title_container: Optional[bs4.Tag] = bs.select_one("h1.entry-title")
        if not title_container:
            log.error(f"{self} Couldn't find raw title container")
            raise ValueError("Raw Title container not found")

        return title_container.text

    async def get_episodes(self) -> Dict[int, AnimeVibeEpisode]:
        bs = await self._req.bs

        links: List[bs4.Tag] = bs.select(".page-nav a")

        episodes: Dict[int, AnimeVibeEpisode] = {}

        for link in links:
            try:
                raw_url = link["href"]
            except KeyError:
                log.warning(f"{self} episode link without url: {link}")
                continue

            try:
                url = URL(raw_url)
            except ValueError:
                log.warning(f"{self} episode link invalid url: {raw_url}")
                continue

            try:
                index = int(link.text) - 1
            except ValueError:
                log.warning(f"{self} couldn't determine episode index: {link.text}")
                continue

            req = Request(f"{{{animevibe_pool}}}{url.path}")
            episode = AnimeVibeEpisode(req)

            episodes[index] = episode

        return episodes

    async def get_episode(self, index: int) -> AnimeVibeEpisode:
        slug, episode_count = await asyncio.gather(self.slug, self.episode_count)
        if not 0 <= index < episode_count:
            raise IndexError("episode index out of range")

        req = Request(f"{{{animevibe_pool}}}/a/{slug}/{index + 1}")
        return AnimeVibeEpisode(req)


animevibe_pool = UrlPool("AnimeVibe", ["https://animevibe.tv", "http://animevibe.tv"])
DefaultUrlFormatter.add_pool(animevibe_pool)

register_source(AnimeVibeAnime)
