__all__ = ["Stream"]

import abc
import asyncio
import logging
from typing import Dict, List, MutableSequence, Optional, Pattern, Union

from grobber.decorators import cached_property
from grobber.request import Request
from grobber.stateful import BsonType, Expiring

log = logging.getLogger(__name__)

VIDEO_MIME_TYPES = ("video/",)


class Stream(Expiring, abc.ABC):
    INCLUDE_CLS = True
    ATTRS = ("external", "links", "poster")
    CHANGING_ATTRS = ("links",)
    EXPIRE_TIME = Expiring.HOUR

    PRIORITY = 100

    HOST = None

    def __repr__(self) -> str:
        return f"{type(self).__qualname__} Stream: {self._req}"

    @classmethod
    async def can_handle(cls, req: Request) -> bool:
        """Check whether this Stream class can handle the request.

        This operation shouldn't actually perform any expensive checks.
        It should merely check whether it's even possible for this Stream to extract
        anything from the request.

        The default implementation compares the Stream.HOST variable to the host
        of the request url (www. is stripped!).

        :param req: request to stream to check
        :return: true if this Stream may be able to extract something from the size, false otherwise
        """
        match = cls.HOST

        if isinstance(match, Pattern):
            url = await req.url
            return bool(match.search(url))
        else:
            host = (await req.yarl).host.lstrip("www.")

            if isinstance(match, str):
                return match == host

            return host in match

    @property
    def persist(self) -> bool:
        """Whether this stream should be stored even if there are neither poster nor links in it

        :return: true to save anyway, false otherwise
        """
        return False

    @property
    @abc.abstractmethod
    async def external(self) -> bool:
        """Indicate whether the links provided by this Stream may be used externally.

        :return: true of the links may be used externally, false otherwise
        """
        ...

    @property
    @abc.abstractmethod
    async def links(self) -> List[str]:
        ...

    @cached_property
    async def poster(self) -> Optional[str]:
        return None

    @cached_property
    async def working(self) -> bool:
        try:
            return len(await self.links) > 0
        except asyncio.CancelledError:
            return False
        except Exception:
            log.exception(f"{self} Couldn't fetch links")
            return False

    @property
    async def working_external_self(self) -> Optional["Stream"]:
        if await self.external and await self.working:
            return self
        else:
            return None

    @staticmethod
    async def get_successful_links(sources: Union[Request, MutableSequence[Request]], *,
                                   use_redirected_url: bool = False) -> List[str]:
        if isinstance(sources, Request):
            sources = [sources]

        for source in sources:
            source.request_kwargs["allow_redirects"] = True

        async def source_check(req: Request) -> bool:
            if await req.head_success:
                content_type = (await req.head_response).content_type

                if not content_type:
                    log.debug(f"No content type for {source}")
                    return False

                if content_type.startswith(VIDEO_MIME_TYPES):
                    return True
            else:
                log.debug(f"{source} didn't make it (probably timeout)!")
                return False

        requests = await Request.all(sources, predicate=source_check)

        urls: List[str] = []
        for req in requests:
            if use_redirected_url:
                url = str(await req.redirected_url)
            else:
                url = await req.url

            urls.append(url)

        log.debug(f"found {len(urls)} working sources")
        return urls

    async def to_dict(self) -> Dict[str, BsonType]:
        links, poster = await asyncio.gather(self.links, self.poster)

        return {"type": type(self).__qualname__,
                "url": self._req.raw_finalised_url,
                "links": links,
                "poster": poster,
                "updated": self.last_update.isoformat()}
