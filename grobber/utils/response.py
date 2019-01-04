__all__ = ["create_response", "error_response"]

from quart import Response, jsonify

from ..exceptions import GrobberException


def create_response(data: dict = None, **kwargs) -> Response:
    data = data or {}
    data.update(kwargs)
    return jsonify(data)


def error_response(exception: GrobberException, *, client_error: bool = None, status_code: int = None) -> Response:
    client_error = client_error if client_error is not None else exception.client_error
    status_code = status_code or exception.status_code

    response = create_response(dict(msg=exception.msg, name=exception.name, client_error=client_error))
    response.status_code = status_code

    return response
