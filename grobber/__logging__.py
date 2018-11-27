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
            "stream": "ext://sys.stdout",
            "formatter": "default"
        }
    },
    "loggers": {
        "grobber": {
            "level": "DEBUG"
        }
    },
    "root": {
        "level": "WARNING",
        "handlers": ["wsgi"]
    }
}
