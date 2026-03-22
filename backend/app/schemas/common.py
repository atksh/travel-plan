from __future__ import annotations

from pydantic import BaseModel, Field


class OkResponse(BaseModel):
    ok: bool = True


class LocationPoint(BaseModel):
    label: str
    lat: float
    lng: float


class EndConstraint(BaseModel):
    kind: str
    minute_of_day: int


class ReplanReadinessOut(BaseModel):
    can_replan: bool
    reasons: list[str] = Field(default_factory=list)
