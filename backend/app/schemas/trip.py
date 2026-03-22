from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.poi import PoiOut


class TripPreferencePatch(BaseModel):
    driving_penalty_weight: float | None = None
    max_continuous_drive_minutes: int | None = None
    preferred_lunch_tags: list[str] | None = None
    preferred_dinner_tags: list[str] | None = None
    must_have_cafe: bool | None = None
    budget_band: str | None = None
    pace_style: str | None = None


class TripCreate(BaseModel):
    plan_date: date
    origin_lat: float
    origin_lng: float
    origin_label: str = "Start"
    dest_lat: float
    dest_lng: float
    dest_label: str = "End"
    departure_window_start_min: int = Field(480, ge=0, le=24 * 60)
    departure_window_end_min: int = Field(540, ge=0, le=26 * 60)
    return_deadline_min: int = Field(1500, ge=0, le=26 * 60)
    weather_mode: str = "normal"
    initial_must_visit_poi_ids: list[int] | None = None
    initial_excluded_poi_ids: list[int] | None = None
    preferences: TripPreferencePatch | None = None

    @model_validator(mode="after")
    def validate_departure_window(self) -> "TripCreate":
        if self.departure_window_end_min < self.departure_window_start_min:
            raise ValueError(
                "departure_window_end_min must be greater than or equal to "
                "departure_window_start_min"
            )
        return self


class TripPatch(BaseModel):
    state: str | None = None
    weather_mode: str | None = None


class CandidateCreate(BaseModel):
    poi_id: int
    must_visit: bool = False
    excluded: bool = False
    user_note: str | None = None


class CandidatePatch(BaseModel):
    must_visit: bool | None = None
    excluded: bool | None = None
    locked_in: bool | None = None
    locked_out: bool | None = None
    user_note: str | None = None
    utility_override: int | None = None


class EventCreate(BaseModel):
    event_type: str
    payload: dict[str, Any] | None = None


class EventOut(BaseModel):
    id: int
    event_type: str
    payload_json: dict[str, Any] | None
    recorded_at: datetime

    model_config = {"from_attributes": True}


class SolveRequest(BaseModel):
    use_traffic_matrix: bool = False


class ReplanRequest(BaseModel):
    current_lat: float | None = None
    current_lng: float | None = None


class TripPreferenceOut(BaseModel):
    driving_penalty_weight: float
    max_continuous_drive_minutes: int
    preferred_lunch_tags: list[str]
    preferred_dinner_tags: list[str]
    must_have_cafe: bool
    budget_band: str | None
    pace_style: str

    model_config = {"from_attributes": True}


class CandidateOut(BaseModel):
    id: int
    poi_id: int
    poi_name: str
    primary_category: str
    status: str
    source: str
    must_visit: bool
    excluded: bool
    locked_in: bool
    locked_out: bool
    user_note: str | None
    utility_override: int | None
    candidate_rank: int | None


class TripOut(BaseModel):
    id: int
    state: str
    plan_date: date
    origin_lat: float
    origin_lng: float
    origin_label: str
    dest_lat: float
    dest_lng: float
    dest_label: str
    departure_window_start_min: int
    departure_window_end_min: int
    return_deadline_min: int
    weather_mode: str

    model_config = {"from_attributes": True}


class SolverRunOut(BaseModel):
    id: int
    objective_value: float | None
    infeasible_reason: str | None
    solve_ms: int

    model_config = {"from_attributes": True}


class RouteLegOut(BaseModel):
    from_sequence_order: int
    to_sequence_order: int
    duration_minutes: int
    distance_meters: int | None = None
    encoded_polyline: str


class PlannedStopOut(BaseModel):
    id: int | None = None
    sequence_order: int
    poi_id: int | None
    poi_name: str
    label: str
    node_kind: str
    lat: float
    lng: float
    arrival_min: int
    departure_min: int
    stay_min: int
    leg_from_prev_min: int | None
    leg_polyline: str | None = None
    status: str

    model_config = {"from_attributes": True}


class SolveSnapshotOut(BaseModel):
    feasible: bool
    objective: float | None
    ordered_poi_ids: list[int] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    solve_ms: int
    solver_run_id: int | None = None
    used_bucket: str
    used_traffic_matrix: bool
    shortlist_ids: list[int] = Field(default_factory=list)
    planned_stops: list[PlannedStopOut] = Field(default_factory=list)
    route_legs: list[RouteLegOut] = Field(default_factory=list)


class TripDetailOut(TripOut):
    preference_profile: TripPreferenceOut | None = None
    candidates: list[CandidateOut] = Field(default_factory=list)
    latest_solve: SolveSnapshotOut | None = None


class SolveResponse(SolveSnapshotOut):
    alternatives: list[CandidateOut] = Field(default_factory=list)


class RoutePreviewOut(BaseModel):
    solve: SolveSnapshotOut | None = None


class ActiveTripStateOut(BaseModel):
    completed_poi_ids: list[int] = Field(default_factory=list)
    in_progress_poi_id: int | None = None
    current_stop: PlannedStopOut | None = None
    next_stop: PlannedStopOut | None = None


class ActiveTripBootstrapOut(BaseModel):
    trip: TripDetailOut
    events: list[EventOut] = Field(default_factory=list)
    pois: list[PoiOut] = Field(default_factory=list)
    active_state: ActiveTripStateOut
