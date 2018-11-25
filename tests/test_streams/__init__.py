from grobber.request import Request


class BasicStreamTest:
    CLS = None
    TESTS = []

    def setUp(self):
        self.requests = list(map(Request, self.TESTS))
        self.streams = list(map(self.CLS, self.requests))

    def test_requests(self):
        for req in self.requests:
            print("looking at", req)
            assert self.CLS.can_handle(req)

    def test_streams(self):
        for stream in self.streams:
            print("looking at", stream)
            assert stream.poster
            assert stream.links
