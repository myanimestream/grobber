from difflib import SequenceMatcher

__all__ = ["get_certainty"]


def get_certainty(a: str, b: str) -> float:
    return round(SequenceMatcher(a=a, b=b).ratio(), 2)
