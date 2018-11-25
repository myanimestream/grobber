from flask import Response

from grobber import app, utils

SHOULD_FAIL = object()


def test_create_response():
    with app.test_request_context():
        resp = utils.create_response()
    assert isinstance(resp, Response)
    assert resp.is_json
    assert resp.get_json()["success"]


def test_cast_argument():
    tests = [
        (["55", int], 55),
        (["tooot", int], SHOULD_FAIL),
        (["tooot", int, 55], 55),
        (["lol", int, None], None),
        (["tooot", lambda v: v], "tooot")
    ]

    for params, success in tests:
        try:
            ret = utils.cast_argument(*params)
            assert ret == success
        except Exception:
            if success is not SHOULD_FAIL:
                raise


def test_add_http_scheme():
    tests = [
        ("google.com", "http://google.com"),
        ("https://google.com", "https://google.com"),
        ("//google.com", "http://google.com"),
        (("search", "https://google.com"), "https://google.com/search")
    ]
    for link, expected in tests:
        base = None
        if not isinstance(link, str):
            link, base = link
        assert utils.add_http_scheme(link, base_url=base) == expected
