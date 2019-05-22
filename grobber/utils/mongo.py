from .text import get_certainty

__all__ = ["normalise_text_score", "full_normalise_text_score"]


def normalise_text_score(query: str, score: float) -> float:
    """Approximate a mongo text score to the range [0, 1].

    Args:
        query: Query which was used
        score: Text score

    Returns:
        An approximation of the normalised text score which is guaranteed
        to be in the closed interval [0, 1].
    """
    words = len(query.split())
    expected_max_score = (words + 1) * .5

    return min(score / expected_max_score, 1)


def full_normalise_text_score(query: str, result: str, score: float) -> float:
    norm_score = normalise_text_score(query, score)
    sim_score = get_certainty(query, result)
    return (norm_score + sim_score) / 2
