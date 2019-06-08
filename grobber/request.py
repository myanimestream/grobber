import asyncio
import inspect
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, TYPE_CHECKING, Tuple, Union, cast

import sentry_sdk
import yarl
from aiohttp import ClientResponse, ClientSession, TCPConnector
from aiohttp.client_exceptions import ClientConnectionError, ClientError, ClientHttpProxyError, \
    ClientProxyConnectionError
from bs4 import BeautifulSoup
from pyppeteer.browser import Browser
from pyppeteer.page import Page
from quart.local import LocalProxy

from .browser import get_browser, load_page
from .decorators import cached_contextmanager, cached_property
from .utils import AsyncFormatter

if TYPE_CHECKING:
    from .url_pool import UrlPool

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/60.0.3112.113 Safari/537.36 "
}


class UrlFormatter(AsyncFormatter):
    _FIELDS: Dict[Any, Any]
    _PROXY_DOMAINS: Dict[str, bool]

    def __init__(self, fields: Dict[Any, Any] = None, proxy_domains: Dict[str, bool] = None) -> None:
        self._FIELDS = fields or {}
        self._PROXY_DOMAINS = proxy_domains or {}

    def add_pool(self, pool: "UrlPool", *, use_proxy: bool = None) -> None:
        self.add_field(str(pool), lambda: pool.url, use_proxy=use_proxy)

    def add_field(self, key: Any, value: Any, *, use_proxy: bool = None) -> None:
        self._FIELDS[key] = value

        if use_proxy is not None:
            self.use_proxy(key, use_proxy)

    def use_proxy(self, key: str, use: bool = True):
        if key not in self._FIELDS:
            raise KeyError("Please use the same key as for the formatting field.")

        self._PROXY_DOMAINS[key] = use

    def add_fields(self, fields: Dict[Any, Any] = None, **kwargs) -> None:
        fields = fields or {}
        fields.update(kwargs)

        for args in fields.items():
            self.add_field(*args)

    async def get_value(self, key: Union[str, int], args: List[Any], kwargs: Dict[Any, Any]) -> Any:
        if key in self._FIELDS:
            value = self._FIELDS[key]

            if inspect.isfunction(value):
                value = value()
                if inspect.isawaitable(value):
                    value = await value

            return value

        return super().get_value(key, args, kwargs)

    def should_use_proxy(self, url: str) -> bool:
        for field, use in self._PROXY_DOMAINS.items():
            if f"{{{field}}}" in url:
                return use


DefaultUrlFormatter = UrlFormatter()

_AIOSESSION = None


def _get_aiosession():
    global _AIOSESSION
    if not _AIOSESSION:
        _AIOSESSION = ClientSession(headers=DEFAULT_HEADERS, connector=TCPConnector(verify_ssl=False))
    return _AIOSESSION


# noinspection PyTypeChecker
AIOSESSION: ClientSession = LocalProxy(_get_aiosession)

PROXY_URL = os.getenv("PROXY_URL")


class Request:
    RESET_ATTRS = ("response", "head_response", "success", "head_success", "text", "json", "bs", "browser", "page")
    RELOAD_ATTRS = RESET_ATTRS

    _url: str
    _yarl: yarl.URL
    _response: ClientResponse
    _head_response: ClientResponse
    _success: bool
    _head_success: bool
    _text: str
    _json: Dict[str, Any]
    _bs: BeautifulSoup
    _browser: Browser
    _page: Page

    def __init__(self, url: str, params: Any = None, headers: Any = None, *,
                 timeout: int = None, max_retries: int = 5, use_proxy: bool = False,
                 get_method: str = "get", head_method: str = "head",
                 **request_kwargs) -> None:
        self._session = AIOSESSION
        self._formatter = DefaultUrlFormatter
        self._retry_count = 0

        self._raw_url = url
        self._params = params
        self._headers = headers

        self._get_method = get_method
        self._head_method = head_method

        self._timeout = timeout
        self._use_proxy = use_proxy or self._formatter.should_use_proxy(self._raw_url)
        self._max_retries = max_retries

        self.request_kwargs = request_kwargs

    def __hash__(self) -> int:
        return hash(self.raw_finalised_url)

    def __eq__(self, other: "Request") -> bool:
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        props: Tuple[str, ...] = (
            hasattr(self, "_url") and "URL",
            hasattr(self, "_response") and "REQ",
            hasattr(self, "_head_response") and "HEAD",
            hasattr(self, "_text") and "TXT",
            hasattr(self, "_json") and "JSON",
            hasattr(self, "_bs") and "BS",
            hasattr(self, "_browser") and "BROWSER",
            hasattr(self, "_page") and "PG",
        )
        cached = ",".join(filter(None, props))

        resp = getattr(self, "_response", None) or getattr(self, "_head_response", None)
        resp = f"{resp.status}" if resp else "ONGOING"

        url = self._url if hasattr(self, "_url") else self.raw_finalised_url
        return f"<{url} [{resp}] ({cached})>"

    @property
    def state(self) -> dict:
        """Get a json serializable dictionary containing the state of this request.

        :return: Dict
        """
        data = {"url": self._raw_url,
                "params": self._params,
                "headers": self._headers,
                "timeout": self._timeout,
                "use_proxy": self._use_proxy,
                "options": self.request_kwargs}
        return {key: value for key, value in data.items() if value}

    @classmethod
    def from_state(cls, state: dict) -> "Request":
        inst = cls(state["url"], state.get("params"), state.get("headers"),
                   timeout=state.get("timeout"), use_proxy=state.get("use_proxy"),
                   **state.get("options", {}))
        return inst

    @classmethod
    def create_soup(cls, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @property
    def headers(self):
        return self._headers

    @property
    def raw_finalised_url(self) -> str:
        return yarl.URL(self._raw_url).update_query(self._params).human_repr()

    @cached_property
    async def url(self) -> str:
        url = yarl.URL(await self._formatter.format(self._raw_url))
        url = url.update_query(self._params)

        sentry_sdk.add_breadcrumb(category="request",
                                  message="Prepared url",
                                  data=dict(raw_url=self._raw_url, url=url.human_repr()),
                                  level="debug")

        return url.human_repr()

    @cached_property
    async def redirected_url(self) -> yarl.URL:
        resp = await self.head_response
        return resp.url

    @cached_property
    async def yarl(self):
        return yarl.URL(await self.url)

    @cached_property
    async def response(self) -> ClientResponse:
        sentry_sdk.add_breadcrumb(category="request",
                                  message="Getting Response",
                                  data=dict(url=self._raw_url),
                                  level="info")
        return await self.perform_request(self._get_method, timeout=self._timeout or 30)

    @cached_property
    async def success(self) -> bool:
        try:
            (await self.response).raise_for_status()
        except (ClientError, asyncio.TimeoutError) as e:
            log.warning(f"Couldn't fetch {self}: {e}")
            return False
        else:
            return True

    @cached_property
    async def head_response(self) -> ClientResponse:
        sentry_sdk.add_breadcrumb(category="request",
                                  message="Getting Head Response",
                                  data=dict(url=self._raw_url),
                                  level="info")
        if hasattr(self, "_response"):
            return self._response

        return await self.perform_request(self._head_method, timeout=self._timeout or 10)

    @cached_property
    async def head_success(self) -> bool:
        try:
            resp = await self.head_response
        except (ClientError, asyncio.TimeoutError) as e:
            log.warning(f"Couldn't head to {self}: {e}")
            return False

        if resp.status == 405:
            log.info(f"{self} HEAD forbidden, using GET")
            return await self.head_success

        try:
            resp.raise_for_status()
        except (ClientError, asyncio.TimeoutError) as e:
            log.warning(f"Couldn't head to {self} ({resp}): {e}")
            return False
        else:
            return True

    @cached_property
    async def text(self) -> str:
        resp = await self.response
        text = await resp.text("utf-8-sig")

        return text.replace("\ufeff", "")

    @cached_property
    async def json(self) -> Dict[str, Any]:
        text = await self.text
        sentry_sdk.add_breadcrumb(category="request",
                                  message="Loading json",
                                  data=dict(url=self._raw_url, text=text),
                                  level="info")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.exception(f"Couldn't parse json {self}:\n\n{text}\n\n")

    @cached_property
    async def bs(self) -> BeautifulSoup:
        text = await self.text
        sentry_sdk.add_breadcrumb(category="request",
                                  message="Creating BeautifulSoup",
                                  data=dict(url=self._raw_url, text=text),
                                  level="info")
        return self.create_soup(text)

    @cached_contextmanager
    async def browser(self, **options):
        browser = await get_browser(**options)
        try:
            yield browser
        finally:
            await browser.close()

    @cached_contextmanager
    async def page(self):
        async with self.browser as browser:
            browser = cast(Browser, browser)

            page = await load_page(browser, await self.url, self._max_retries)

            try:
                yield page
            finally:
                await page.close()

    async def staggered_request(self, method: str, url: str, **kwargs) -> ClientResponse:
        requests = set()

        timeout = 1
        timeout_mult = 1.5

        while True:
            req = self._session.request(method, url, **kwargs)
            requests.add(req)

            done_fs, requests = await asyncio.wait(requests, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)

            done = next(iter(done_fs), None)
            if done:
                resp = done.result()
                break

            timeout *= timeout_mult

        for req in requests:
            req.cancel()

        return resp

    async def perform_request(self, method: str, **kwargs) -> ClientResponse:
        options = self.request_kwargs.copy()
        options.update(headers=self.headers, timeout=self._timeout)
        options.update(kwargs)

        url = await self.url
        resp = None

        while self._retry_count < self._max_retries:
            self._retry_count += 1

            if self._use_proxy:
                options["proxy"] = PROXY_URL

            try:
                options.pop("timeout", None)
                resp = await self.staggered_request(method, url, **options)
            except (ClientProxyConnectionError, ClientHttpProxyError) as e:
                log.info(f"{self} proxy error: {e}, trying again. try {self._retry_count}/{self._max_retries}")
                continue
            except ClientConnectionError as e:
                log.info(f"{self} connectiong error: {e}, trying again. try {self._retry_count}/{self._max_retries}")
                self._use_proxy = True
                continue

            if resp.status in {403, 429, 503, 529} and self._retry_count <= self._max_retries:
                log.info(f"{self} request failed ({resp.status}). " +
                         ("Already using proxy, trying again" if self._use_proxy else "Trying again with proxy") +
                         f" try {self._retry_count}/{self._max_retries}")

                if method == self._head_method:
                    method = self._get_method
                    log.info(f"{self} switched from head to get method!")

                self._use_proxy = True
                continue

            break

        if not resp:
            raise TimeoutError(f"Timed out after {self._retry_count}/{self._max_retries} retries!")

        return resp

    def reload(self):
        log.debug(f"{self} reloading...")
        self.reset(self.RELOAD_ATTRS)

    def reset(self, attrs: Iterable[str] = None) -> None:
        attrs = attrs or self.RESET_ATTRS
        for attr in attrs:
            try:
                delattr(self, attr)
            except AttributeError:
                pass
            except Exception as e:
                log.warning(f"{self} couldn't delete attr {attr} {e}")

    @staticmethod
    async def try_req(req: "Request", *, predicate: Callable[["Request"], Awaitable[bool]] = None) -> Optional[
        "Request"]:
        """Return request if it passes predicate, otherwise None

        :param req: Request to check
        :param predicate: Predicate to check on req, defaults to head_success
        :return: req if it passes predicate, else None
        """
        if predicate is None:
            if await req.head_success:
                return req
        else:
            res = predicate(req)
            if inspect.isawaitable(res):
                res = await res

            if res:
                return req

        return None

    @staticmethod
    async def first(requests: Iterable["Request"], *, timeout: float = None,
                    predicate: Callable[["Request"], Awaitable[bool]] = None) -> Optional["Request"]:
        """Get first request that fulfills predicate (or None)

        :param requests: Iterable of requests
        :param timeout: Timeout for ALL requests together
        :param predicate: Predicate to fulfill (defaults to head_success)
        :return: Optional Request instance
        """
        coros = {Request.try_req(request, predicate=predicate) for request in requests}

        while coros:
            done, coros = await asyncio.wait(coros, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                break

            request = next(iter(done)).result()

            if request:
                for coro in coros:
                    coro.cancel()

                return request

        return None

    @staticmethod
    async def all(requests: Iterable["Request"], *, timeout: float = None,
                  predicate: Callable[["Request"], Awaitable[bool]] = None) -> List["Request"]:
        """Get all requests that fulfill predicate

        :param requests: Iterable of Request instances
        :param timeout: timeout for ALL requests together
        :param predicate: condition for a Request to pass (defaults to head_success)
        :return: List of Requests that fulfilled predicate
        """
        wrapped = {Request.try_req(request, predicate=predicate) for request in requests}
        if not wrapped:
            return []

        done, _ = await asyncio.wait(wrapped, timeout=timeout,
                                     return_when=asyncio.ALL_COMPLETED)
        return list(filter(None, (task.result() for task in done)))
