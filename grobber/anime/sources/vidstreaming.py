import logging
import re
from typing import AsyncIterator, List, Optional, Pattern

from grobber.decorators import cached_property
from grobber.languages import Language
from grobber.request import DefaultUrlFormatter, Request
from grobber.url_pool import UrlPool
from grobber.utils import add_http_scheme, get_certainty
from . import register_source
from ..models import Anime, Episode, SearchResult

log = logging.getLogger(__name__)

RE_TITLE_EXTRACTOR: Pattern = re.compile(r"\s*(.+?)( \(Dub\))? Episode \d+\s*$")
RE_HEADER_EXTRACTOR: Pattern = re.compile(r"\s*(.+?)( \(Dub\))? Episode \d+(?: English Subbed)?\s*$")
RE_URL_SLUG_EXTRACTOR: Pattern = re.compile(r"([^/]+-)\d+$")

vidstreaming_pool = UrlPool("Vidstreaming", ["https://vidstreaming.io"])
DefaultUrlFormatter.add_field("VIDSTREAMING_URL", lambda: vidstreaming_pool.url)


class VidstreamingEpisode(Episode):
    @cached_property
    async def streams_page(self) -> Request:
        bs = await self._req.bs
        frame = bs.select_one("div.play-video iframe")
        return Request(add_http_scheme(frame["src"]))

    @cached_property
    async def raw_streams(self) -> List[str]:
        streams_page = await self.streams_page
        bs = await streams_page.bs

        stream_urls = [await streams_page.url]
        streams = bs.select("""li.linkserver[data-status="1"]""")

        for stream in streams:
            href = stream["data-video"]
            url = add_http_scheme(href)
            stream_urls.append(url)

        return stream_urls


class VidstreamingAnime(Anime):
    ATTRS = ("url_slug",)
    EPISODE_CLS = VidstreamingEpisode

    @cached_property
    async def is_dub(self) -> False:
        await self.parse_header()
        return self._is_dub

    @cached_property
    async def language(self) -> Language:
        return Language.ENGLISH

    @cached_property
    async def title(self) -> str:
        await self.parse_header()
        return self._title

    @cached_property
    async def thumbnail(self) -> Optional[str]:
        return None

    async def get_episodes(self) -> List[EPISODE_CLS]:
        bs = await self._req.bs
        links = bs.select("ul.items li.video-block a")
        episodes = []
        for link in links:
            href = link["href"]
            req = Request(f"{{VIDSTREAMING_URL}}{href}")
            episode = self.EPISODE_CLS(req)
            episodes.append(episode)

        return episodes

    @cached_property
    async def url_slug(self) -> str:
        url = await self._req.url
        match = RE_URL_SLUG_EXTRACTOR.search(url)
        return match.group(1)

    async def get_episode(self, index: int) -> EPISODE_CLS:
        url_slug = await self.url_slug
        url = f"{{VIDSTREAMING_URL}}/videos/{url_slug}{index + 1}"
        return self.EPISODE_CLS(Request(url))

    @classmethod
    async def search(cls, query: str, *, dubbed: bool = False, language: Language = Language.ENGLISH) -> AsyncIterator[SearchResult]:
        if language != Language.ENGLISH:
            return

        bs = await Request("{VIDSTREAMING_URL}/search.html", dict(keyword=query)).bs
        links = bs.select("ul.items li.video-block a")

        for link in links:
            url = "{VIDSTREAMING_URL}" + link["href"]
            title_container = link.select_one("div.name").text
            match = RE_TITLE_EXTRACTOR.match(title_container)
            title = match.group(1)
            is_dub = bool(match.group(2))

            if dubbed != is_dub:
                continue

            thumbnail = link.select_one("div.picture img")["src"]

            anime = cls(Request(url), data=dict(title=title, thumbnail=thumbnail, is_dub=is_dub))

            similarity = get_certainty(query, title)
            yield SearchResult(anime, similarity)

    # noinspection PyPropertyAccess
    async def parse_header(self) -> None:
        header = (await self._req.bs).select_one("div.video-info h1").text
        match = RE_HEADER_EXTRACTOR.match(header)
        self.title = match.group(1)
        self.is_dub = bool(match.group(2))


register_source(VidstreamingAnime)