import asyncio
import inspect
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple, Union

import pyppeteer
import yarl
from aiohttp import ClientResponse, ClientSession
from aiohttp.client_exceptions import ClientError
from bs4 import BeautifulSoup
from pyppeteer.browser import Browser
from pyppeteer.page import Page

from .decorators import cached_contextmanager, cached_property
from .utils import AsyncFormatter

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:64.0) Gecko/20100101 Firefox/64.0"
}


class UrlFormatter(AsyncFormatter):
    _FIELDS: Dict[Any, Any]

    def __init__(self, fields: Dict[Any, Any] = None) -> None:
        self._FIELDS = fields or {}

    def add_field(self, key: Any, value: Any) -> None:
        self._FIELDS[key] = value

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


DefaultUrlFormatter = UrlFormatter()

# AIOSESSION = ClientSession(trust_env=True)
AIOSESSION = ClientSession()

CHROME_WS = os.getenv("CHROME_WS")


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

    def __init__(self, url: str, params: Any = None, headers: Any = None, timeout: int = None, **request_kwargs) -> None:
        self._raw_url = url
        self._params = params
        self._headers = headers
        self._timeout = timeout

        self.request_kwargs = request_kwargs

        self._formatter = DefaultUrlFormatter
        self._session = AIOSESSION

    def __hash__(self) -> int:
        return hash(self._raw_url)

    def __eq__(self, other: "Request") -> bool:
        return self._raw_url == other._raw_url and self._params == other._params

    def __repr__(self) -> str:
        props: Tuple[str, ...] = (
            hasattr(self, "_response") and "REQ",
            hasattr(self, "_text") and "TXT",
            hasattr(self, "_bs") and "BS"
        )
        cached = ",".join(filter(None, props))

        url = self._url if hasattr(self, "_url") else self._raw_url
        return f"<{url} ({cached})>"

    @property
    def state(self) -> dict:
        data = {"url": self._raw_url}
        if self._params:
            data["params"] = self._params
        if self._headers:
            data["headers"] = self._params
        if self._timeout:
            data["timeout"] = self._timeout
        if self.request_kwargs:
            data["options"] = self.request_kwargs
        return data

    @classmethod
    def from_state(cls, state: dict) -> "Request":
        inst = cls(state["url"], state.get("params"), state.get("headers"), state.get("timeout"), **state.get("options", {}))
        return inst

    @classmethod
    def create_soup(cls, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @property
    def headers(self):
        headers = DEFAULT_HEADERS.copy()
        if self._headers:
            headers.update(self._headers)
        return headers

    @cached_property
    async def url(self) -> str:
        raw_url = await self._formatter.format(self._raw_url)
        return yarl.URL(raw_url).update_query(self._params).human_repr()

    @cached_property
    async def yarl(self):
        return yarl.URL(await self.url)

    @cached_property
    async def response(self) -> ClientResponse:
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
        if hasattr(self, "_response"):
            return self._response

        return await self.perform_request("head", timeout=self._timeout or 5)

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
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.exception(f"Couldn't parse json:\n\n{text}\n\n")

    @cached_property
    async def bs(self) -> BeautifulSoup:
        return self.create_soup(await self.text)

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
        options.update(kwargs)

        return await self._session.request(method, await self.url, **options)

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
