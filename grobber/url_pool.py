import logging
from asyncio import Lock
from datetime import datetime, timedelta
from typing import List

from . import locals
from .exceptions import GrobberException
from .request import Request

log = logging.getLogger(__name__)


class UrlPool:

    def __init__(self, name: str, urls: List[str], *, strip_slash: bool = True, ttl: int = 3600) -> None:
        self._url = None
        self._next_update = None

        self.name = name
        self.urls = urls

        self.strip_slash = strip_slash
        self.ttl = timedelta(seconds=ttl)
        self._lock = Lock()

    def __str__(self) -> str:
        return f"<Pool {self.name}: {self._url}>"

    @property
    async def url(self) -> str:
        async with self._lock:
            if (not self._next_update) or datetime.now() > self._next_update:
                await self.fetch()

            if (not self._next_update) or datetime.now() > self._next_update:
                log.debug(f"searching new url for {self}")
                await self.update_url()
                self._next_update = datetime.now() + self.ttl
                await self.upload()

            return self.prepare_url(self._url)

    async def fetch(self) -> None:
        doc = await locals.url_pool_collection.find_one(self.name)
        if not doc:
            log.debug(f"creating pool for {self}")
        else:
            log.debug(f"{self} initialising from database")
            self._url = doc["url"]
            self._next_update = doc["next_update"]

    async def upload(self) -> None:
        await locals.url_pool_collection.update_one(dict(_id=self.name), {"$set": dict(url=self._url, next_update=self._next_update)}, upsert=True)

    def prepare_url(self, url: str) -> str:
        if self.strip_slash:
            url = url.rstrip("/")

        return url

    async def update_url(self) -> None:
        requests = [Request(url, allow_redirects=True) for url in self.urls]
        req = await Request.first(requests)

        if req:
            self._url = str((await req.head_response).url)

            log.debug(f"{req} successful, moving to front! ({self._url})")
            self.urls.insert(0, self.urls.pop(requests.index(req)))
        else:
            raise GrobberException(f"{self} No working url found")
