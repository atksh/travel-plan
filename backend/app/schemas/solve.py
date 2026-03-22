from __future__ import annotations

from pydantic import BaseModel, Field


class SolveSummaryOut(BaseModel):
    feasible: bool
    score: float | None = None
    total_drive_minutes: int
    total_stay_minutes: int
    total_distance_meters: int
    start_time_min: int
    end_time_min: int


class SolveStopOut(BaseModel):
    sequence_order: int
    node_kind: str
    place_id: int | None = None
    label: str
    lat: float
    lng: float
    arrival_min: int
    departure_min: int
    stay_min: int
    leg_from_prev_min: int | None = None
    status: str


class RouteLegOut(BaseModel):
    from_sequence_order: int
    to_sequence_order: int
    duration_minutes: int
    distance_meters: int | None = None
    encoded_polyline: str


class RuleResultOut(BaseModel):
    rule_id: int
    status: str
    score_impact: float = 0
    explanation: str


class CandidateDiagnosticOut(BaseModel):
    candidate_id: int
    status: str
    explanation: str
    blocking_rule_ids: list[int] = Field(default_factory=list)


class SolveAlternativeOut(BaseModel):
    label: str
    description: str
    candidate_id: int | None = None
    place_id: int | None = None


class SolvePayloadOut(BaseModel):
    summary: SolveSummaryOut
    stops: list[SolveStopOut] = Field(default_factory=list)
    route_legs: list[RouteLegOut] = Field(default_factory=list)
    selected_place_ids: list[int] = Field(default_factory=list)
    unselected_candidates: list[CandidateDiagnosticOut] = Field(default_factory=list)
    rule_results: list[RuleResultOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    alternatives: list[SolveAlternativeOut] = Field(default_factory=list)


class PreviewRequestIn(BaseModel):
    workspace_version: int | None = None
    draft_candidate_patches: list[dict] = Field(default_factory=list)
    draft_rule_patches: list[dict] = Field(default_factory=list)
    draft_order_edits: list[int] = Field(default_factory=list)


class PreviewOut(BaseModel):
    preview_id: str
    workspace_version: int
    based_on_run_id: int | None = None
    solve: SolvePayloadOut


class SolveRequestIn(BaseModel):
    workspace_version: int
    preview_id: str | None = None


class SolveAcceptedOut(BaseModel):
    solve_run_id: int
    accepted: bool = True
    solve: SolvePayloadOut


class SolveRunListItemOut(BaseModel):
    solve_run_id: int
    run_kind: str
    accepted_at: str
    summary: SolveSummaryOut


class SolveRunListOut(BaseModel):
    items: list[SolveRunListItemOut] = Field(default_factory=list)
