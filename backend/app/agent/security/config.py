from __future__ import annotations

from pathlib import Path

import yaml

from app.agent.security.types import Checkpoint, CheckpointConfig, SecurityConfig


def load_security_config(path: Path | None = None) -> SecurityConfig:
    if path is None:
        path = Path(__file__).resolve().parents[4] / "configs" / "security.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return SecurityConfig(**raw)


def checkpoint_configs(config: SecurityConfig) -> dict[Checkpoint, CheckpointConfig]:
    """Return a fully-populated map (missing checkpoints get defaults)."""
    result: dict[Checkpoint, CheckpointConfig] = {}
    for cp in Checkpoint:
        result[cp] = config.checkpoints.get(cp) or CheckpointConfig()
    return result
