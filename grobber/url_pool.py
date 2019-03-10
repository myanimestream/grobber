import logging
from asyncio import Lock
from datetime import datetime, timedelta
from typing import List

from . import locals
from .exceptions import GrobberException
from .request import Request

log = logging.getLogger(__name__)


class UrlPool:
    """Pool of possible urls which provides easy access to a working one.

    Attributes:
          name (str): Name given to the pool
          urls (List[str]): List of the possible urls
          strip_slash (bool): Whether or not tailing slashes should be removed
          ttl (timedelta): Time until the current url expires

    """

    def __init__(self, name: str, urls: List[str], *, strip_slash: bool = True, ttl: int = 3600) -> None:
        self._url = None
        self._next_update = None

        self.name = name
        self.urls = urls

        self.strip_slash = strip_slash
        self.ttl = timedelta(seconds=ttl)

        self.__lock = None

    def __str__(self) -> str:
        return f"<Pool {self.name}: {self._url}>"

    @property
    def _lock(self) -> Lock:
        if not self.__lock:
            self.__lock = Lock()
        return self.__lock

    @property
    def needs_update(self) -> bool:
        """Whether the current url is outdated."""
        return (not self._next_update) or datetime.now() > self._next_update

    @property
    async def url(self) -> str:
        """Current url."""
        async with self._lock:
            if self.needs_update:
                await self.fetch()

            if self.needs_update:
                log.debug(f"searching new url for {self}")
                await self.update_url()
                self._next_update = datetime.now() + self.ttl
                await self.upload()

            return self.prepare_url(self._url)

    async def fetch(self) -> None:
        """Get the current url from the database."""
        doc = await locals.url_pool_collection.find_one(self.name)
        if not doc:
            log.debug(f"creating pool for {self}")
        else:
            log.debug(f"{self} initialising from database")
            self._url = doc["url"]
            self._next_update = doc["next_update"]

    async def upload(self) -> None:
        """Upload the current url to the database."""
        await locals.url_pool_collection.update_one(dict(_id=self.name), {"$set": dict(url=self._url, next_update=self._next_update)}, upsert=True)

    def prepare_url(self, url: str) -> str:
        """Prepare an url to be used as the current url.

        This function is performed for all urls returned by `url`
        """
        if self.strip_slash:
            url = url.rstrip("/")

        return url

    async def update_url(self) -> None:
        """Search for a working url.

        This is automatically called.
        """
        requests = [Request(url, allow_redirects=True) for url in self.urls]
        req = await Request.first(requests)

        if req:
            self._url = str((await req.head_response).url)

            log.debug(f"{req} successful, moving to front! ({self._url})")
            self.urls.insert(0, self.urls.pop(requests.index(req)))
        else:
            raise GrobberException(f"{self} No working url found {requests}")
