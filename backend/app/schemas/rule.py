from __future__ import annotations

from pydantic import BaseModel, Field


class RuleTargetIn(BaseModel):
    kind: str
    value: str | int | float | None = None
    data: dict = Field(default_factory=dict)


class RuleTargetOut(BaseModel):
    kind: str
    value: str | int | float | None = None
    data: dict = Field(default_factory=dict)


class RuleCreateIn(BaseModel):
    rule_kind: str
    scope: str
    mode: str
    weight: float | None = None
    target: RuleTargetIn
    operator: str
    parameters: dict = Field(default_factory=dict)
    carry_forward_strategy: str
    label: str
    description: str | None = None
    created_by_surface: str = "ui"


class RulePatchIn(BaseModel):
    mode: str | None = None
    weight: float | None = None
    target: RuleTargetIn | None = None
    operator: str | None = None
    parameters: dict | None = None
    carry_forward_strategy: str | None = None
    label: str | None = None
    description: str | None = None


class RuleOut(BaseModel):
    id: int
    trip_id: int
    rule_kind: str
    scope: str
    mode: str
    weight: float | None = None
    target: RuleTargetOut
    operator: str
    parameters: dict = Field(default_factory=dict)
    carry_forward_strategy: str
    label: str
    description: str | None = None
    created_by_surface: str


class RuleListOut(BaseModel):
    items: list[RuleOut] = Field(default_factory=list)
