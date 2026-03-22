from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import EndConstraint, LocationPoint
from app.schemas.place import PlaceSummaryOut
from app.schemas.rule import RuleOut
from app.schemas.solve import SolvePayloadOut


class TripSummaryOut(BaseModel):
    id: int
    title: str
    plan_date: date
    state: str
    timezone: str


class TripDetailOut(TripSummaryOut):
    origin: LocationPoint
    destination: LocationPoint
    departure_window_start_min: int
    departure_window_end_min: int
    end_constraint: EndConstraint
    context: dict = Field(default_factory=dict)


class TripListOut(BaseModel):
    items: list[TripSummaryOut] = Field(default_factory=list)


class TripCreateIn(BaseModel):
    title: str = Field(..., min_length=1)
    plan_date: date
    origin: LocationPoint
    destination: LocationPoint
    departure_window_start_min: int = Field(..., ge=0)
    departure_window_end_min: int = Field(..., ge=0)
    end_constraint: EndConstraint
    timezone: str
    context: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_window(self) -> "TripCreateIn":
        if self.departure_window_end_min < self.departure_window_start_min:
            raise ValueError(
                "departure_window_end_min must be greater than or equal to departure_window_start_min"
            )
        return self


class TripPatchIn(BaseModel):
    title: str | None = None
    state: str | None = None
    origin: LocationPoint | None = None
    destination: LocationPoint | None = None
    departure_window_start_min: int | None = Field(default=None, ge=0)
    departure_window_end_min: int | None = Field(default=None, ge=0)
    end_constraint: EndConstraint | None = None
    timezone: str | None = None
    context: dict | None = None


class CandidateCreateIn(BaseModel):
    place_id: int
    priority: str = "normal"


class StayOverrideOut(BaseModel):
    min: int | None = None
    preferred: int | None = None
    max: int | None = None


class TimePreferenceOut(BaseModel):
    arrive_after_min: int | None = None
    arrive_before_min: int | None = None
    depart_after_min: int | None = None
    depart_before_min: int | None = None


class CandidatePatchIn(BaseModel):
    candidate_state: str | None = None
    priority: str | None = None
    locked_in: bool | None = None
    locked_out: bool | None = None
    utility_override: int | None = None
    stay_override: StayOverrideOut | None = None
    time_preference: TimePreferenceOut | None = None
    manual_order_hint: int | None = None
    user_note: str | None = None


class CandidateOut(BaseModel):
    id: int
    place_id: int
    candidate_state: str
    priority: str
    locked_in: bool
    locked_out: bool
    utility_override: int | None = None
    stay_override: StayOverrideOut
    time_preference: TimePreferenceOut
    manual_order_hint: int | None = None
    user_note: str | None = None
    place: PlaceSummaryOut


class CandidateListOut(BaseModel):
    items: list[CandidateOut] = Field(default_factory=list)


class TripWorkspaceOut(BaseModel):
    trip: TripDetailOut
    workspace_version: int
    candidates: list[CandidateOut] = Field(default_factory=list)
    rules: list[RuleOut] = Field(default_factory=list)
    latest_accepted_run: SolvePayloadOut | None = None
    planning_summary: dict | None = None
