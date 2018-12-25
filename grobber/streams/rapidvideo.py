from typing import List, Optional

from . import register_stream
from ..decorators import cached_property
from ..models import Stream
from ..request import Request


class RapidVideo(Stream):
    HOST = "rapidvideo.com"

    @cached_property
    async def poster(self) -> Optional[str]:
        link_container = (await self._req.bs).select_one("video#videojs")
        if not link_container:
            return None
        link = link_container.attrs.get("poster")
        if link and await Request(link).head_success:
            return link

    @cached_property
    async def links(self) -> List[str]:
        sources = [Request(source["src"], timeout=5) for source in (await self._req.bs).select("video source")]
        return await Stream.get_successful_links(sources)

    @cached_property
    async def external(self) -> bool:
        return True


register_stream(RapidVideo)
