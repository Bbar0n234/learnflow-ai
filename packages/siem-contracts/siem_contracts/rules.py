"""Correlation rule configuration models."""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field


class ThresholdRuleConfig(BaseModel):
    """Configuration for threshold-based rules."""

    rule_type: Literal["threshold"] = "threshold"
    event_type_pattern: str = Field(
        ..., description="Pattern for matching event types (supports wildcards)"
    )
    threshold: int = Field(..., ge=1, description="Event count threshold")
    window: int = Field(..., ge=1, description="Time window in seconds")
    group_key: str | None = Field(None, description="Grouping key (ip, user_id, etc)")


class SequenceRuleConfig(BaseModel):
    """Configuration for sequence-based rules."""

    rule_type: Literal["sequence"] = "sequence"
    event_a_pattern: str = Field(..., description="Pattern for first event in sequence")
    event_b_pattern: str = Field(
        ..., description="Pattern for second event in sequence"
    )
    window: int = Field(..., ge=1, description="Time window in seconds")
    group_key: str | None = Field(None, description="Grouping key (optional)")


class AggregateRuleConfig(BaseModel):
    """Configuration for aggregate-based rules."""

    rule_type: Literal["aggregate"] = "aggregate"
    event_type_pattern: str = Field(
        ..., description="Pattern for matching event types (supports wildcards)"
    )
    threshold: int = Field(..., ge=1, description="Event count threshold")
    window: int = Field(..., ge=1, description="Time window in seconds")


RuleConfig = Union[ThresholdRuleConfig, SequenceRuleConfig, AggregateRuleConfig]
