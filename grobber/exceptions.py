from enum import IntEnum


class GrobberExceptionType(IntEnum):
    UNKNOWN = 0
    GENERAL = 1
    INVALID_REQUEST = 2

    UID_UNKNOWN = 101
    ANIME_NOT_FOUND = 102
    EPISODE_NOT_FOUND = 103
    STREAM_NOT_FOUND = 104
    SOURCE_NOT_FOUND = 105


class GrobberException(Exception):
    msg: str
    code: GrobberExceptionType

    def __init__(self, msg: str = None, code: GrobberExceptionType = None):
        super().__init__(code, msg)
        self.msg = msg or "Unknown Error"
        self.code = code or GrobberExceptionType.UNKNOWN


class InvalidRequest(GrobberException):
    def __init__(self, msg: str = None):
        super().__init__(msg or "Invalid Request!", GrobberExceptionType.INVALID_REQUEST)


class UIDUnknown(GrobberException):
    def __init__(self, uid: str):
        super().__init__(f"Nothing with uid {uid} found", GrobberExceptionType.UID_UNKNOWN)


class AnimeNotFound(GrobberException):
    def __init__(self, query: str, **filters) -> None:
        msg = f"Couldn't find anime \"{query}\""
        if filters:
            msg += f" with filters {', '.join(f'{key}={value}' for key, value in filters.items())}"

        super().__init__(msg, GrobberExceptionType.ANIME_NOT_FOUND)


class EpisodeNotFound(GrobberException):
    def __init__(self, index: int, anime_length: int):
        text = f"No episode {index} found, only {anime_length} episodes!"
        if index == anime_length:
            text += " Did you forgot that the first episode has index 0?"

        super().__init__(text, GrobberExceptionType.EPISODE_NOT_FOUND)


class StreamNotFound(GrobberException):
    def __init__(self):
        super().__init__(f"Couldn't extract a stream for this anime", GrobberExceptionType.STREAM_NOT_FOUND)


class SourceNotFound(GrobberException):
    def __init__(self):
        super().__init__(f"Source not found", GrobberExceptionType.SOURCE_NOT_FOUND)
