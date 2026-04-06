"""Centralized logging setup: structlog over stdlib via ProcessorFormatter."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Any

import structlog
import yaml


def setup_logging(log_level: str, config_path: Path, log_file: str = "") -> None:
    """Initialize structlog + stdlib logging.

    Args:
        log_level: Root log level (e.g. "info", "debug").
        config_path: Path to configs/logging.yaml.
        log_file: Optional file path for log output. Empty = stdout only.
    """
    cfg = _load_config(config_path)

    use_json = cfg.get("format") == "json"

    if use_json:
        console_renderer: structlog.types.Processor = (
            structlog.processors.JSONRenderer()
        )
        file_renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        console_renderer = structlog.dev.ConsoleRenderer()
        file_renderer = structlog.dev.ConsoleRenderer(colors=False)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Per-library overrides from YAML
    overrides: dict[str, dict[str, Any]] = {}
    for lib_name, level_str in cfg.get("overrides", {}).items():
        overrides[lib_name] = {"level": level_str.upper()}

    formatters: dict[str, Any] = {
        "console": {
            "()": structlog.stdlib.ProcessorFormatter,
            "foreign_pre_chain": shared_processors,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                console_renderer,
            ],
        },
    }
    if log_file:
        formatters["file"] = {
            "()": structlog.stdlib.ProcessorFormatter,
            "foreign_pre_chain": shared_processors,
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                file_renderer,
            ],
        }

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": formatters,
            "handlers": _build_handlers(log_file),
            "root": {
                "level": log_level.upper(),
                "handlers": list(_build_handlers(log_file).keys()),
            },
            "loggers": overrides,
        }
    )


def _build_handlers(log_file: str) -> dict[str, Any]:
    """Build logging handlers dict. Always stdout; optionally a file."""
    handlers: dict[str, Any] = {
        "default": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "console",
        },
    }
    if log_file:
        handlers["file"] = {
            "class": "logging.FileHandler",
            "filename": log_file,
            "mode": "a",
            "formatter": "file",
        }
    return handlers


def _load_config(path: Path) -> dict[str, Any]:
    """Load logging YAML config, returning empty dict on failure."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}
