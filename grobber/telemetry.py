__all__ = ["API_REQUESTS", "API_EXCEPTIONS", "LANGUAGE_COUNTER", "SOURCE_COUNTER", "ANIME_SEARCH_TIME", "ANIME_RESOLVE_TIME", "ANIME_QUERY_TYPE"]

import logging
from typing import Tuple

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest, multiprocess

log = logging.getLogger(__name__)


def get_metrics() -> Tuple[bytes, str]:
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)

    return generate_latest(registry), CONTENT_TYPE_LATEST


API_REQUESTS = Counter("api_requests", "Amount of api requests", ("method", "endpoint",))
API_EXCEPTIONS = Counter("api_exceptions", "Amount of Grobber exceptions", ("name",))

LANGUAGE_COUNTER = Counter("language_requests", "Langauge/Translation type chosen", ("language", "translation_type"))
SOURCE_COUNTER = Counter("source_requests", "Langauge/Translation type chosen", ("source",))

ANIME_SEARCH_TIME = Histogram("anime_search_time_seconds", "Time spent searching for anime")
ANIME_RESOLVE_TIME = Histogram("anime_resolve_time_seconds", "Time spent resolving anime")
ANIME_QUERY_TYPE = Counter("anime_query_type", "Query used to retrieve anime data", ("type",))
