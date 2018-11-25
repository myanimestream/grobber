import sys

CONFIG = {
    "version": 1,
    "formatters": {
        "default": {
            "()": "colorlog.ColoredFormatter",
            "format": "[{asctime}] {log_color}{levelname}{reset} in {blue}{module}{reset}: {message}",
            "style": "{"
        }
    },
    "handlers": {
        "wsgi": {
            "class": "logging.StreamHandler",
            "stream": "ext://flask.logging.wsgi_errors_stream",
            "formatter": "default"
        }
    },
    "loggers": {
        "urllib3": {
            "level": "WARNING"
        }
    },
    "root": {
        "level": "NOTSET",
        "handlers": ["wsgi"]
    }
}

sys.modules[__name__] = CONFIG
