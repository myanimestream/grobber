__all__ = ["AnimeNotFound", "EpisodeNotFound", "StreamNotFound", "SourceNotFound"]

from ..exceptions import GrobberException


class AnimeNotFound(GrobberException):
    def __init__(self, query: str, **filters) -> None:
        msg = f"Couldn't find anime \"{query}\""
        if filters:
            msg += f" with filters {', '.join(f'{key}={value}' for key, value in filters.items())}"

        super().__init__(msg)


class EpisodeNotFound(GrobberException):
    def __init__(self, index: int, anime_length: int):
        text = f"No episode {index} found, only {anime_length} episode(s)!"
        if index == anime_length:
            text += " Did you forgot that the first episode has index 0?"

        super().__init__(text, client_error=True)


class StreamNotFound(GrobberException):
    def __init__(self):
        super().__init__(f"Couldn't extract a stream for this anime", client_error=True)


class SourceNotFound(GrobberException):
    def __init__(self):
        super().__init__(f"Source not found", client_error=True)
