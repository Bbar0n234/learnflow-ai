"""The ``SKILL_CONTEXT_WRITE`` security checkpoint wiring.

Skill-context documents are a persistent injection point — their content is
surfaced to the assistant as trusted per-user context on every future
``load_skill``. So the REST write must run through a dedicated checkpoint, by the
precedent of ``CUSTOM_INSTRUCTIONS_WRITE`` / ``KS_WRITE_REST``. These tests pin
that the checkpoint exists, is inbound, resolves a classifier-enabled config from
the shipped ``configs/security.yaml``, and that both deterministic detectors
(canary, unicode) apply to it.
"""

from __future__ import annotations

import pytest
from app.agent.security.config import checkpoint_configs, load_security_config
from app.agent.security.detectors.canary import CanaryDetector
from app.agent.security.detectors.unicode import UnicodeDetector
from app.agent.security.types import Checkpoint, Direction, direction_of


@pytest.mark.unit
def test_skill_context_write_checkpoint_is_inbound() -> None:
    # A write-time injection point is classified as inbound content.
    assert direction_of(Checkpoint.SKILL_CONTEXT_WRITE) is Direction.INBOUND


@pytest.mark.unit
def test_skill_context_write_config_resolves_with_classifier_enabled() -> None:
    # The shipped config carries a real block for the checkpoint (not the empty
    # default): classifier on, and a description + specifics guiding the verdict.
    configs = checkpoint_configs(load_security_config())

    cfg = configs[Checkpoint.SKILL_CONTEXT_WRITE]
    assert cfg.classifier_enabled is True
    assert cfg.description != ""
    assert cfg.specifics != ""


@pytest.mark.unit
def test_canary_detector_applies_to_skill_context_write() -> None:
    assert Checkpoint.SKILL_CONTEXT_WRITE in CanaryDetector.applies_to


@pytest.mark.unit
def test_unicode_detector_applies_to_skill_context_write() -> None:
    assert Checkpoint.SKILL_CONTEXT_WRITE in UnicodeDetector.applies_to
