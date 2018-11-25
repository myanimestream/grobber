import logging
from datetime import datetime, timedelta
from typing import List

from . import proxy
from .exceptions import GrobberException
from .request import DefaultUrlFormatter, Request

log = logging.getLogger(__name__)


class UrlPool:

    def __init__(self, name: str, urls: List[str], *, strip_slash: bool = True, ttl: int = 3600) -> None:
        self._url = None
        self._next_update = None

        self.name = name
        self.urls = urls

        self.strip_slash = strip_slash
        self.ttl = timedelta(seconds=ttl)

    def __str__(self) -> str:
        return f"<Pool {self.name}>"

    @property
    def url(self) -> str:
        if (not self._next_update) or datetime.now() > self._next_update:
            self.fetch()

        if (not self._next_update) or datetime.now() > self._next_update:
            log.debug(f"searching new url for {self}")
            self.update_url()
            self._next_update = datetime.now() + self.ttl
            self.upload()

        return self.prepare_url(self._url)

    def fetch(self) -> None:
        doc = proxy.url_pool_collection.find_one(self.name)
        if not doc:
            log.debug(f"creating pool for {self}")
        else:
            log.debug("initialising from database")
            self._url = doc["url"]
            self._next_update = doc["next_update"]

    def upload(self) -> None:
        proxy.url_pool_collection.update_one(dict(_id=self.name), {"$set": dict(url=self._url, next_update=self._next_update)}, upsert=True)

    def prepare_url(self, url: str) -> str:
        if self.strip_slash:
            url = url.rstrip("/")

        return url

    def update_url(self) -> None:
        for i, url in enumerate(self.urls):
            req = Request(url, allow_redirects=True)
            log.debug(f"trying {req}")
            if req.head_success:
                self.urls.insert(0, self.urls.pop(i))
                self._url = req.head_response.url
                log.debug(f"{req} successful, moving to front! ({self._url})")
                break
        else:
            raise GrobberException(f"{self} No working url found")


gogoanime_pool = UrlPool("GogoAnime", ["https://gogoanimes.co", "http://gogoanimes.co"])
masteranime_pool = UrlPool("MasterAnime", ["https://www.masterani.me"])
nineanime_pool = UrlPool("9anime", ["https://9anime.to/", "http://9anime.to"])

DefaultUrlFormatter.add_field("GOGOANIME_URL", lambda: gogoanime_pool.url)
DefaultUrlFormatter.add_field("MASTERANIME_URL", lambda: masteranime_pool.url)
DefaultUrlFormatter.add_field("9ANIME_URL", lambda: nineanime_pool.url)
