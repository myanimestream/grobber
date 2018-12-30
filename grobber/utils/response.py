__all__ = ["create_response", "error_response"]

from quart import Response, jsonify

from ..exceptions import GrobberException


def create_response(data: dict = None, success: bool = True, **kwargs) -> Response:
    data = data or {}
    data.update(kwargs)
    data["success"] = success
    return jsonify(data)


def error_response(exception: GrobberException, *, client_error: bool = None, status_code: int = None) -> Response:
    response = create_response(dict(msg=exception.msg, name=exception.name), success=False)

    if exception.client_error or client_error is True:
        response.status_code = 400

    if status_code:
        response.status_code = status_code

    return response
