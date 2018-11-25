import logging.config

from . import __logging__
from .__info__ import *

logging.config.dictConfig(__logging__)

from .app import app
