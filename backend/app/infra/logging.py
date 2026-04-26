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
        _security_event_processor,
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


_IDENTIFIER_KEYS: frozenset[str] = frozenset(
    {"user_id", "thread_id", "project_id", "scope"}
)
_METADATA_KEYS: frozenset[str] = frozenset(
    {"checkpoint", "verdict", "detection_layer", "retries", "tool", "detector"}
)


def _security_event_processor(
    logger: Any,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Normalize security-events so feat-005 SIEM can tail them off log stream.

    Call sites write fields inline (``user_id=...``, ``verdict=...``). The
    processor groups them into the canonical ``identifiers{}`` /
    ``metadata{}`` sub-dicts so downstream processors (Phase 2:
    ``security_events`` table) have a stable contract.
    """
    if not event_dict.get("security_event"):
        return event_dict

    level = str(event_dict.get("level") or method_name).upper()
    event_dict.setdefault("severity", level)
    if "security_event_type" not in event_dict and "event" in event_dict:
        event_dict["security_event_type"] = event_dict["event"]

    identifiers = event_dict.get("identifiers")
    if not isinstance(identifiers, dict):
        identifiers = {}
    for key in _IDENTIFIER_KEYS:
        if key in event_dict and key not in identifiers:
            identifiers[key] = event_dict.pop(key)
    event_dict["identifiers"] = identifiers

    metadata = event_dict.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    for key in _METADATA_KEYS:
        if key in event_dict and key not in metadata:
            metadata[key] = event_dict.pop(key)
    event_dict["metadata"] = metadata

    return event_dict


def _load_config(path: Path) -> dict[str, Any]:
    """Load logging YAML config, returning empty dict on failure."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}
