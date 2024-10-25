import logging
import sys
from typing import Any, Callable, Optional

import orjson
import structlog
from environs import Env

from app.config import LOG_LEVEL

env = Env()
env.read_env()

def orjson_dumps(v: Any, *, default: Optional[Callable[[Any], Any]]) -> str:
    return orjson.dumps(v, default=default).decode()

def configure_logging():
    logging.basicConfig(level=LOG_LEVEL, format="%(message)s", stream=sys.stdout)

    shared_processors = [
        structlog.stdlib.filter_by_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if sys.stderr.isatty():
        # For console output, use a more compact format
        processors = shared_processors + [
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            )
        ]
    else:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=orjson_dumps),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

configure_logging()

def get_logger(module: str, log_type: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(module).bind(module=module, type=log_type)
