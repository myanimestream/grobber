import asyncio
import logging
import os
from typing import List

import pyppeteer
import yarl
from pyppeteer.browser import Browser
from pyppeteer.errors import TimeoutError as PyppeteerTimeoutError
from pyppeteer.page import Page
from quart.local import LocalProxy

log = logging.getLogger(__name__)

CHROME_WS = os.getenv("CHROME_WS")
PROXY_URL = os.getenv("PROXY_URL")


async def get_browser(*, args: List[str] = None, **options) -> Browser:
    if args is None:
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--window-size=1920x1080",
        ]
        if PROXY_URL:
            scheme = yarl.URL(PROXY_URL).scheme
            host = PROXY_URL[len(scheme) + 3:]
            args.append(f"--proxy-server=\"http={host};https={host}\"")

    if CHROME_WS:
        qs = "?" + "&".join(args) if args else ""
        log.debug("connecting to external chrome")
        browser = await asyncio.wait_for(pyppeteer.connect(browserWSEndpoint=CHROME_WS + qs, **options), timeout=20)
    else:
        log.debug("launching local chrome")
        browser = await pyppeteer.launch(args=args, headless=True, **options)

    log.debug(f"created browser: {browser}")
    return browser


BLOCKED_RESOURCE_TYPES = {
    "image",
    "media",
    "font",
    "texttrack",
    "object",
    "beacon",
    "csp_report",
    "imageset",
}

_BLOCKED_HOSTS = None


def _load_blocked_hosts():
    global _BLOCKED_HOSTS

    if not _BLOCKED_HOSTS:
        with open("data/blocked_hosts") as file:
            _BLOCKED_HOSTS = {line.strip() for line in file.readlines()}
            log.info(f"loaded {len(BLOCKED_HOSTS)} hosts")
    return _BLOCKED_HOSTS


BLOCKED_HOSTS = LocalProxy(_load_blocked_hosts)


async def load_page(browser: Browser, url: str, max_retries: int) -> Page:
    log.debug("creating a new page")
    page = await browser.newPage()
    await page.setRequestInterception(True)

    requests_blocked = 0
    requests_allowed = 0

    @page.on("request")
    async def on_request(request: pyppeteer.page.Request):
        nonlocal requests_allowed, requests_blocked

        if request.resourceType in BLOCKED_RESOURCE_TYPES:
            requests_blocked += 1
            await request.abort()
        elif yarl.URL(request.url).host in BLOCKED_HOSTS:
            requests_blocked += 1
            await request.abort()
        else:
            requests_allowed += 1
            await request.continue_()

    log.debug(f"navigating to {url}")
    for attempt in range(max_retries):
        try:
            await page.goto(url, timeout=25000, waitUntil="networkidle2")
            break
        except PyppeteerTimeoutError:
            log.info(f"{url} timed out, trying again {attempt + 1} / {max_retries}")
    else:
        raise TimeoutError("Timeout exceeded")

    requests_total = requests_allowed + requests_blocked
    log.debug(f"{page.url} Blocked {requests_blocked}/{requests_total} requests ({round(100 * requests_blocked / requests_total)}%)")

    return page
