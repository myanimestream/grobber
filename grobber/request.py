import asyncio
import inspect
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple, Union

import pyppeteer
import sentry_sdk
import yarl
from aiohttp import ClientResponse, ClientSession
from aiohttp.client_exceptions import ClientError
from bs4 import BeautifulSoup
from pyppeteer.browser import Browser
from pyppeteer.page import Page

from .decorators import cached_contextmanager, cached_property
from .telemetry import HTTP_REQUESTS
from .utils import AsyncFormatter

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:64.0) Gecko/20100101 Firefox/64.0"
}


class UrlFormatter(AsyncFormatter):
    _FIELDS: Dict[Any, Any]
    _PROXY_DOMAINS: Dict[str, bool]

    def __init__(self, fields: Dict[Any, Any] = None, proxy_domains: Dict[str, bool] = None) -> None:
        self._FIELDS = fields or {}
        self._PROXY_DOMAINS = proxy_domains or {}

    def add_field(self, key: Any, value: Any) -> None:
        self._FIELDS[key] = value

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

AIOSESSION = ClientSession(headers=DEFAULT_HEADERS)

CHROME_WS = os.getenv("CHROME_WS")
PROXY_URL = os.getenv("PROXY_URL")


async def get_browser(**options) -> Browser:
    if CHROME_WS:
        return await pyppeteer.connect(browserWSEndpoint=CHROME_WS, **options)
    else:
        return await pyppeteer.launch(**options)


class Request:
    ATTRS = ()

    _url: str
    _response: ClientResponse
    _success: bool
    _text: str
    _json: Dict[str, Any]
    _bs: BeautifulSoup

    def __init__(self, url: str, params: Any = None, headers: Any = None, *,
                 timeout: int = None, max_retries: int = 5, use_proxy: bool = False,
                 **request_kwargs) -> None:
        self._session = AIOSESSION
        self._formatter = DefaultUrlFormatter
        self._retry_count = 0

        self._raw_url = url
        self._params = params
        self._headers = headers

        self._timeout = timeout
        self._use_proxy = use_proxy or self._formatter.should_use_proxy(self._raw_url)
        self._max_retries = max_retries

        self.request_kwargs = request_kwargs

    def __hash__(self) -> int:
        return hash(self._raw_url)

    def __eq__(self, other: "Request") -> bool:
        return self._raw_url == other._raw_url and self._params == other._params

    def __repr__(self) -> str:
        props: Tuple[str, ...] = (
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

        url = self._url if hasattr(self, "_url") else self._raw_url
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
    async def yarl(self):
        return yarl.URL(await self.url)

    @cached_property
    async def response(self) -> ClientResponse:
        sentry_sdk.add_breadcrumb(category="request",
                                  message="Getting Response",
                                  data=dict(url=self._raw_url),
                                  level="info")
        return await self.perform_request("get")

    @cached_property
    async def success(self) -> bool:
        try:
            (await self.response).raise_for_status()
        except (ClientError, asyncio.TimeoutError) as e:
            log.warning(f"Couldn't fetch to {self}: {e}")
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

        return await self.perform_request("head", timeout=self._timeout or 7)

    @cached_property
    async def head_success(self) -> bool:
        try:
            (await self.head_response).raise_for_status()
        except (ClientError, asyncio.TimeoutError) as e:
            log.warning(f"Couldn't head to {self}: {e}")
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
    async def browser(self, **options) -> Browser:
        browser = await get_browser(**options)
        try:
            yield browser
        finally:
            await browser.close()

    @cached_contextmanager
    async def page(self) -> Page:
        browser: Browser
        async with self.browser as browser:
            page = await browser.newPage()
            await page.goto(await self.url)

            try:
                yield page
            finally:
                await page.close()

    async def perform_request(self, method: str, **kwargs) -> ClientResponse:
        options = self.request_kwargs.copy()
        options.update(headers=self.headers, timeout=self._timeout)

        if self._use_proxy:
            log.debug(f"{self} using proxy")
            options["proxy"] = PROXY_URL

        self.track_telemetry(self._raw_url, method, self._use_proxy)

        options.update(kwargs)

        url = await self.url
        resp = await self._session.request(method, url, **options)

        if resp.status == 403 and self._retry_count <= self._max_retries:
            log.info(f"{self} request blocked (403 forbidden). " +
                     ("Already using proxy, trying again" if self._use_proxy else "Trying again with proxy") +
                     f" try {self._retry_count + 1}/{self._max_retries}")

            self._use_proxy = True
            self._retry_count += 1
            resp = await self.perform_request(method, **kwargs)

        return resp

    def track_telemetry(self, url: str, method: str, using_proxy: bool) -> None:
        host = yarl.URL(url).host
        HTTP_REQUESTS.labels(host, method, using_proxy).inc()

    @staticmethod
    async def try_req(req: "Request", *, predicate: Callable[["Request"], Awaitable[bool]] = None) -> Optional["Request"]:
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
    async def all(requests: Iterable["Request"], *, timeout: float = None, predicate: Callable[["Request"], Awaitable[bool]] = None) -> ["Request"]:
        wrapped = {Request.try_req(request, predicate=predicate) for request in requests}
        if not wrapped:
            return []

        done, _ = await asyncio.wait(wrapped, timeout=timeout,
                                     return_when=asyncio.ALL_COMPLETED)
        return list(filter(None, (task.result() for task in done)))
