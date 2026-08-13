"""Minimal structlog configuration for the executor service."""

import logging

import structlog


def configure_logging(log_level: str) -> None:
    """Configure structlog's filtering bound logger at `log_level`.

    Internal service, single machine client, no library loggers to bridge —
    JSON lines straight to stdout via `PrintLoggerFactory`, no stdlib
    logging integration.
    """
    level = logging.getLevelNamesMapping()[log_level.upper()]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            # Renders `exc_info=True`/an exception instance into a
            # formatted traceback string under the `exception` key. Without
            # it, `exc_info=True` reaches `JSONRenderer` unrendered and
            # leaks into the JSON output as a useless literal `"exc_info":
            # true` (T3.4 finding — runner.py's `"job launch failed"` ERROR
            # log had no traceback until this was added).
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
