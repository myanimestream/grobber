import asyncio
import os
from typing import Any, Dict, NamedTuple, Optional

import aiohttp


class AriasStatus(NamedTuple):
    download_id: str
    state: str
    result: Optional[dict]
    error: Optional[str]

    @classmethod
    def build(cls, data: Dict[str, Any]) -> "AriasStatus":
        return AriasStatus(data["id"], data["state"], data.get("result"), data.get("error"))


class AriasDownload(NamedTuple):
    client: "Arias"
    download_id: str

    async def get_status(self) -> AriasStatus:
        return await self.client.get_status(self.download_id)

    async def wait_for_download(self) -> AriasStatus:
        return await self.client.wait_for_download(self.download_id)


class Arias:
    url: str
    callback_url: str

    aiosession: aiohttp.ClientSession
    downloads: Dict[str, asyncio.Future]

    def __init__(self, url: str, callback_url: str) -> None:
        self.url = url
        self.callback_url = callback_url

        self.aiosession = aiohttp.ClientSession()
        self.downloads = {}

    def get_download(self, download_id: str) -> AriasDownload:
        return AriasDownload(self, download_id)

    async def download(self, url: str, name: str) -> AriasDownload:
        params = dict(url=url, name=name, callback=self.callback_url)

        async with self.aiosession.get(f"{self.url}/download", params=params) as resp:
            data = await resp.json()
        return self.get_download(data["id"])

    async def wait_for_download(self, download_id: str) -> AriasStatus:
        future = self.downloads.get("download_id")
        if not future:
            future = self.downloads[download_id] = asyncio.Future()

        return await future

    async def get_status(self, download_id: str) -> AriasStatus:
        async with self.aiosession.get(f"{self.url}/status", params={"id": download_id}) as resp:
            data = await resp.json()
        return AriasStatus.build(data)

    def receive_callback(self, data: Dict[str, Any]) -> None:
        status = AriasStatus.build(data)
        future = self.downloads.pop(status.download_id, None)
        if future:
            future.set_result(status)


ARIAS_URL = os.getenv("ARIAS_URL")
ARIAS_CALLBACK_URL = os.getenv("ARIAS_CALLBACK_URL", "http://localhost/arias")

DEFAULT_ARIAS = Arias(ARIAS_URL, ARIAS_CALLBACK_URL)

download = DEFAULT_ARIAS.download
get_status = DEFAULT_ARIAS.get_status

receive_callback = DEFAULT_ARIAS.receive_callback
