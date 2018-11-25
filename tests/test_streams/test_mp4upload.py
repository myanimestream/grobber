from unittest import TestCase

from grobber.streams.mp4upload import Mp4Upload
from . import BasicStreamTest


class TestMp4Upload(BasicStreamTest, TestCase):
    CLS = Mp4Upload
    TESTS = [
        "https://www.mp4upload.com/embed-h2yq5i3c7xo7.html",
        "https://www.mp4upload.com/embed-1934b3ai70n2.html",
        "https://www.mp4upload.com/embed-8yajb93uspci.html"
    ]
