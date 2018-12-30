class GrobberException(Exception):
    msg: str
    client_error: bool

    def __init__(self, msg: str = None, client_error: bool = False):
        super().__init__(msg)
        self.msg = msg or "Unknown Error"
        self.client_error = client_error

    @property
    def name(self) -> str:
        return type(self).__qualname__


class InvalidRequest(GrobberException):
    def __init__(self, msg: str = None):
        super().__init__(msg or "Invalid Request!", client_error=True)


class UIDInvalid(GrobberException):
    def __init__(self, uid: str) -> None:
        super().__init__(f"Uid invalid: {uid}", client_error=True)


class UIDUnknown(GrobberException):
    def __init__(self, uid: str):
        super().__init__(f"Nothing with uid {uid} found", client_error=True)
