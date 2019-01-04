class GrobberException(Exception):
    msg: str
    client_error: bool
    status_code: int

    def __init__(self, msg: str = None, client_error: bool = False, status_code: int = None):
        super().__init__(msg)
        self.msg = msg or "Unknown Error"
        self.client_error = client_error
        self.status_code = status_code or 400 if client_error else 500

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
        super().__init__(f"Nothing with uid {uid} found", client_error=True, status_code=404)
