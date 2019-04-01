from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_PAUSED, STATE_RUNNING
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from grobber.locals import source_index_collection, source_index_meta_collection
from .index_scrapers import IndexScraperCategory, scrape_indices

__all__ = ["create_scheduler", "get_scheduler", "start_scheduler"]


async def _scrape_new() -> None:
    await scrape_indices(source_index_collection, source_index_meta_collection, IndexScraperCategory.NEW)


async def _scrape_ongoing() -> None:
    await scrape_indices(source_index_collection, source_index_meta_collection, IndexScraperCategory.ONGOING)


async def _scrape_full() -> None:
    await scrape_indices(source_index_collection, source_index_meta_collection, IndexScraperCategory.FULL)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(_scrape_new, CronTrigger(day="*"))
    scheduler.add_job(_scrape_ongoing, IntervalTrigger(weeks=2))
    scheduler.add_job(_scrape_full, IntervalTrigger(weeks=16))

    return scheduler


_SCHEDULER: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global _SCHEDULER

    if not _SCHEDULER:
        _SCHEDULER = create_scheduler()

    return _SCHEDULER


def start_scheduler() -> None:
    scheduler = get_scheduler()

    if scheduler.state == STATE_PAUSED:
        scheduler.resume()
    elif scheduler.state != STATE_RUNNING:
        scheduler.start()
