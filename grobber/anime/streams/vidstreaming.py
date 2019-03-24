import logging
import re
from typing import Dict, List, Optional

from grobber.decorators import cached_property
from grobber.request import Request
from grobber.utils import parse_js_json
from . import register_stream
from ..models import Stream

log = logging.getLogger(__name__)

RE_EXTRACT_SETUP = re.compile(r"playerInstance\.setup\((.+?)\);", re.DOTALL)
RE_EXTRACT_URL_VIDEO = re.compile(r"urlVideo\s*=\s*[\"'`](.+)[\"'`];")


def _extract_variables(text: str) -> Dict[str, str]:
    variables: Dict[str, str] = {}

    try:
        url_video = RE_EXTRACT_URL_VIDEO.search(text).group(1)
    except (IndexError, TypeError):
        pass
    else:
        variables["urlVideo"] = url_video

    return variables


def extract_player_data(text: str) -> dict:
    match = RE_EXTRACT_SETUP.search(text)
    if not match:
        return {}

    variables = _extract_variables(text)

    return parse_js_json(match.group(1), variables=variables)


class Vidstreaming(Stream):
    ATTRS = ("player_data",)

    HOST = "vidstreaming.io"

    @cached_property
    async def player_data(self) -> dict:
        data = extract_player_data(await self._req.text)
        if not data:
            log.debug(f"Couldn't find player data {self}")

        return data

    @cached_property
    async def poster(self) -> Optional[str]:
        link = (await self.player_data).get("image")
        if link and await Request(link).head_success:
            return link
        return None

    @cached_property
    async def links(self) -> List[str]:
        raw_sources = (await self.player_data).get("sources")
        if not raw_sources:
            return []

        sources = [Request(source["file"]) for source in raw_sources]
        log.debug(f"found sources {sources}")
        return await self.get_successful_links(sources)

    @cached_property
    async def external(self) -> bool:
        return True


register_stream(Vidstreaming)
