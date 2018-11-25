from enum import IntEnum


class GrobberExceptionType(IntEnum):
    UNKNOWN = 0
    GENERAL = 1
    INVALID_REQUEST = 2

    UIDUnknown = 101
    EPISODE_NOT_FOUND = 102
    STREAM_NOT_FOUND = 103

    USER_NOT_FOUND = 201


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
    def __init__(self, query: str):
        super().__init__(f"No anime with uid \"{query}\" found", GrobberExceptionType.UIDUnknown)


class EpisodeNotFound(GrobberException):
    def __init__(self, index: int, anime_length: int):
        super().__init__(f"No episode {index} found, only {anime_length} episodes! Did you forgot that the first episode is index 0?",
                         GrobberExceptionType.EPISODE_NOT_FOUND)


class StreamNotFound(GrobberException):
    def __init__(self):
        super().__init__(f"Couldn't extract a stream for this anime", GrobberExceptionType.STREAM_NOT_FOUND)


class UserNotFound(GrobberException):
    def __init__(self, username: str):
        super().__init__(f"No user with username \"{username}\" found", GrobberExceptionType.USER_NOT_FOUND)