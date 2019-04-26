import re
from typing import List, Optional

from bs4 import BeautifulSoup

from grobber.decorators import cached_property
from grobber.request import Request
from . import register_stream
from ..models import Stream


class RapidVideo(Stream):
    HOST = re.compile(r"rapidvideo\.\w{2,3}")

    @cached_property
    async def bs(self) -> BeautifulSoup:
        # get the cookie
        await self._req.response
        self._req.reload()
        # hopefully use the cookie?
        bs = await self._req.bs
        return bs

    @cached_property
    async def poster(self) -> Optional[str]:
        link_container = (await self.bs).select_one("video#videojs")
        if not link_container:
            return None
        link = link_container.attrs.get("poster")
        if link and await Request(link).head_success:
            return link

    @cached_property
    async def links(self) -> List[str]:
        bs = await self.bs

        sources = [Request(source["src"], timeout=10) for source in bs.select("video#videojs source")]
        return await Stream.get_successful_links(sources)

    @cached_property
    async def external(self) -> bool:
        return True


register_stream(RapidVideo)
