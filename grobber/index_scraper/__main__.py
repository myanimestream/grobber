import asyncio
import time
from datetime import timedelta
from enum import EnumMeta
from typing import Any, Callable, Dict, Tuple, TypeVar

import click

from grobber.index_scraper import Medium, MediumGroup
from grobber.languages import Language
from grobber.locals import source_index_meta_collection
from grobber.uid import MediumType
from .common import IndexScraperCategory
from .medium import MediumData
from .medium_access import SearchItem, search_media


class EnumType(click.Choice):
    def __init__(self, enum: EnumMeta):
        self._enum = enum
        member_map: Dict[str, Any] = enum.__members__

        super().__init__(member_map, case_sensitive=False)

    def convert(self, value: str, param: click.Argument, ctx: click.Context):
        if isinstance(value, self._enum):
            return value

        return self._enum[super().convert(value, param, ctx).upper()]


@click.group()
def cli() -> None:
    ...


@cli.command()
def start() -> None:
    """Start the scheduler.

    This will run the scrapers in intervals
    to keep the data updated.
    """
    from . import schedule
    loop = asyncio.get_event_loop()

    schedule.start_scheduler()

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass

    click.echo("exited")


@cli.command()
@click.argument("categories", nargs=-1, type=EnumType(IndexScraperCategory))
def scrape(categories: Tuple[IndexScraperCategory]) -> None:
    """Run the scraper for the given categories.

    If no categories provided, all scrapers are ran.
    """
    from . import scrape_indices
    from grobber.locals import source_index_collection

    categories_str: str = ", ".join(map(str, categories)) or "ALL"

    start_time = time.time()
    click.echo(f"scraping categories: {categories_str}")
    asyncio.run(scrape_indices(source_index_collection, source_index_meta_collection, *categories))

    click.echo(f"done after {timedelta(seconds=time.time() - start_time)}", color="green")


@cli.command()
def initdb() -> None:
    """Initialise the database.

    This adds the required indexes to the related collections.
    There's no need to do this manually however, the program
    already does it automatically when required.
    """
    from . import add_collection_indexes
    from grobber.locals import source_index_collection

    asyncio.run(add_collection_indexes(source_index_collection))


def _get_origin(medium: MediumData) -> str:
    if isinstance(medium, Medium):
        return medium.source_cls
    elif isinstance(medium, MediumGroup):
        return ", ".join(map(_get_origin, medium.media))
    else:
        return "unknown"


def format_medium(medium: MediumData) -> str:
    headline = f"{medium.title}"
    aliases_str = ",".join(f"\"{alias}\"" for alias in medium.aliases)
    if aliases_str:
        headline = f"{headline} ({aliases_str})"

    underline = len(medium.title) * "="

    dub_str = "dubbed" if medium.dubbed else "subbed"
    ep_count_str = "???" if medium.episode_count is None else medium.episode_count

    return f"{headline}\n" \
        f"{underline}\n" \
        f"language: {medium.language} {dub_str}\n" \
        f"eps: {ep_count_str}\n" \
        f"from: {_get_origin(medium)}"


T = TypeVar("T")


def format_search_item(search_item: SearchItem, item_formatter: Callable[[T], str]) -> str:
    item_str = item_formatter(search_item.item)
    return f"{item_str}\nscore: {search_item.score}"


@cli.command()
@click.argument("query", nargs=-1, type=str, required=True)
@click.option("-t", "--type", "medium_type", type=EnumType(MediumType), default=MediumType.ANIME)
@click.option("-l", "--language", type=EnumType(Language), default=Language.ENGLISH)
@click.option("-d", "--dubbed", type=bool, default=False)
@click.option("-p", "--page", type=int, default=0)
def search(query: Tuple[str], medium_type: MediumType, language: Language, dubbed: bool, page: int) -> None:
    from grobber.locals import source_index_collection

    results = asyncio.run(search_media(source_index_collection, medium_type, " ".join(query), language=language, dubbed=dubbed, page=page))
    click.echo("\n\n".join(format_search_item(result, format_medium) for result in results))


if __name__ == "__main__":
    cli()
