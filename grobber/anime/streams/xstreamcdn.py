import logging
from typing import List, Optional

from grobber.decorators import cached_property
from grobber.request import Request
from . import register_stream
from ..models import Stream

log = logging.getLogger(__name__)

BASE_URL = "https://www.xstreamcdn.com"
API_URL = f"{BASE_URL}/api/source/{{video_id}}"


class XStreamCDN(Stream):
    ATTRS = ("video_id", "player_data",)

    HOST = "xstreamcdn.com"

    @cached_property
    async def video_id(self) -> str:
        url = await self._req.yarl
        return url.name

    @cached_property
    async def player_data(self) -> dict:
        video_id = await self.video_id
        req = Request(API_URL.format(video_id=video_id), get_method="post")
        return await req.json

    @cached_property
    async def poster(self) -> Optional[str]:
        data = await self.player_data

        try:
            relative_url = data["player"]["poster_file"]
        except (KeyError, TypeError):
            return None

        return f"{BASE_URL}{relative_url}"

    @cached_property
    async def links(self) -> List[str]:
        data = await self.player_data

        try:
            raw_sources = data["data"]
        except KeyError:
            return []

        if not isinstance(raw_sources, list):
            return []

        sources: List[Request] = []
        for raw_source in raw_sources:
            try:
                file = raw_source["file"]
            except KeyError:
                continue

            sources.append(Request(file))

        log.debug(f"found sources {sources}")
        return await self.get_successful_links(sources, use_redirected_url=True)

    @cached_property
    async def external(self) -> bool:
        return True


register_stream(XStreamCDN)
