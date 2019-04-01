import asyncio
import time
from datetime import timedelta
from enum import EnumMeta
from typing import Any, Dict, Tuple

import click

from grobber.locals import source_index_meta_collection
from .common import IndexScraperCategory


class EnumType(click.Choice):
    def __init__(self, enum: EnumMeta):
        self._enum = enum
        member_map: Dict[str, Any] = enum.__members__

        super().__init__(member_map, case_sensitive=False)

    def convert(self, value: str, param: click.Argument, ctx: click.Context):
        return self._enum[super().convert(value, param, ctx).upper()]


@click.group()
def cli() -> None:
    ...


@cli.command()
def start() -> None:
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
    from . import scrape_indices
    from grobber.locals import source_index_collection

    categories_str: str = ", ".join(map(str, categories)) or "ALL"

    start_time = time.time()
    click.echo(f"scraping categories: {categories_str}")
    asyncio.run(scrape_indices(source_index_collection, source_index_meta_collection, *categories))

    click.echo(f"done after {timedelta(seconds=time.time() - start_time)}", color="green")


@cli.command()
def initdb() -> None:
    from . import add_collection_indexes
    from grobber.locals import source_index_collection

    asyncio.run(add_collection_indexes(source_index_collection))


if __name__ == "__main__":
    cli()
