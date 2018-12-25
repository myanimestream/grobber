# Uses ip lock, but good proof of concept

import logging
from typing import Any, Dict, List, Optional

from pyppeteer.page import Page, PageError

from . import register_stream
from ..decorators import cached_property
from ..models import Stream
from ..request import Request

log = logging.getLogger(__name__)

# noinspection BadExpressionStatementJS
EXTRACT_DATA_SCRIPT = """(element) => {
    function absoluteUrl(url) {
        let a = document.createElement("a");
        a.href = url;
        return a.href;
    }

    return {
        source: absoluteUrl(element.getAttribute("src")),
        poster: absoluteUrl(element.getAttribute("poster"))
    };
}"""


class Openload(Stream):
    ATTRS = ("player_data",)
    PRIORITY = 5

    HOST = "openload.co"

    @cached_property
    async def player_data(self) -> Dict[str, Any]:
        try:
            page: Page
            async with self._req.page as page:
                await page.click("div#videooverlay")
                data = await page.querySelectorEval("video#olvideo_html5_api", EXTRACT_DATA_SCRIPT)

            return data
        except PageError as e:
            log.warning(f"couldn't access {self} because {e}")

        return {}

    @cached_property
    async def poster(self) -> Optional[str]:
        link = (await self.player_data).get("poster")
        if link and await Request(link).head_success:
            return link
        return None

    @cached_property
    async def links(self) -> List[str]:
        source = (await self.player_data).get("source")

        if source and await Request(source).head_success:
            return [source]

    @cached_property
    async def external(self) -> bool:
        return False


register_stream(Openload)
