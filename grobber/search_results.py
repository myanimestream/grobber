from datetime import datetime
from typing import Any, Dict, List, Optional

from grobber.locals import anime_collection, search_results_collection
from grobber.uid import MediaType


async def find_cached_searches(media_type: MediaType, query: str, max_results: int = None) -> List[Dict[str, Any]]:
    """Return search results that loosely match the search request"""
    collection_name = anime_collection.name if media_type == MediaType.ANIME else "mango"

    search_pipeline = [
        {"$match": {
            "$text": {"$search": query},
            "type": media_type.value,
        }},
        {"$addFields": {"score": {"$meta": "textScore"}}},
        {"$sort": {"score": -1}},
        {"$unwind": {"path": "$results"}},
    ]

    if max_results:
        search_pipeline.append({"$limit": max_results})

    lookup_pipeline = [
        {"$lookup": {
            "from": collection_name,
            "localField": "results",
            "foreignField": "_id",
            "as": "results",
        }},
        {"$unwind": {"path": "$results"}},
        {"$group": {
            "_id": None,
            "results": {"$addToSet": "$results"}
        }}
    ]

    documents = await search_results_collection.aggregate(search_pipeline + lookup_pipeline).to_list(None)

    if not documents:
        return []

    return documents[0].get("results", [])


async def get_cached_searches(media_type: MediaType, query: str, requested_results: int = None) -> Optional[List[Dict[str, Any]]]:
    """Return the documents which match the search request exactly.

    Use :func:`find_cached_searches` to loosely search for cached results.
    """
    collection_name = anime_collection.name if media_type == MediaType.ANIME else "mango"

    pipeline = [
        {"$match": {
            "query": query,
            "type": media_type.value,
            "requested_results": {"$gte": requested_results}
        }},
        {"$unwind": {"path": "$results"}},
        {"$lookup": {
            "from": collection_name,
            "localField": "results",
            "foreignField": "_id",
            "as": "results",
        }},
        {"$unwind": {"path": "$results"}},
        {"$group": {
            "_id": None,
            "results": {"$addToSet": "$results"}
        }}
    ]

    documents = await search_results_collection.aggregate(pipeline).to_list(None)

    if not documents:
        return None

    return documents[0].get("results")


async def store_cached_search(media_type: MediaType, query: str, requested_results: int, uids: List[str]):
    """Store the provided search request such that it can be retrieved later on"""
    await search_results_collection.insert_one({
        "type": media_type.value,
        "query": query,
        "requested_results": requested_results,
        "results": list(uids),
        "created": datetime.now()
    })
