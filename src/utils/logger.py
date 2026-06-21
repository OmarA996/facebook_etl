from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

import structlog

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_FORMAT = os.getenv("LOG_FORMAT", "console").lower()  # console | json
_LOG_FILE = os.getenv("LOG_FILE", "logs/etl.log")

_configured = False


def configure_logger() -> None:
    """Configure structlog + stdlib logging once at startup.

    Reads LOG_LEVEL (default INFO), LOG_FORMAT (console|json, default console),
    and LOG_FILE (default logs/etl.log) from the environment.
    Writes to stdout and a rotating file (10 MB × 5 backups).
    """
    global _configured
    if _configured:
        return
    _configured = True

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    use_json = _LOG_FORMAT == "json"
    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)
    root.handlers = []

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    try:
        Path(_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            _LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except OSError:
        pass


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
