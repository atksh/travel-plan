from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ReplanReadinessOut
from app.schemas.solve import PreviewOut, SolveAcceptedOut, SolvePayloadOut, SolveStopOut
from app.schemas.trip import TripDetailOut


class ExecutionSessionOut(BaseModel):
    execution_session_id: int
    active_run_id: int | None = None
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    current_stop_id: int | None = None


class ExecutionStartOut(BaseModel):
    execution_session_id: int
    trip_state: str
    active_run_id: int


class ExecutionEventCreateIn(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)


class ExecutionEventOut(BaseModel):
    event_id: int
    event_type: str
    payload: dict = Field(default_factory=dict)
    recorded_at: str


class ExecutionBootstrapOut(BaseModel):
    trip: TripDetailOut
    execution_session: ExecutionSessionOut
    active_solve: SolvePayloadOut
    events: list[ExecutionEventOut] = Field(default_factory=list)
    current_stop: SolveStopOut | None = None
    next_stop: SolveStopOut | None = None
    replan_readiness: ReplanReadinessOut


class ReplanPreviewRequestIn(BaseModel):
    workspace_version: int | None = None
    current_context: dict = Field(default_factory=dict)
    draft_candidate_patches: list[dict] = Field(default_factory=list)
    draft_rule_patches: list[dict] = Field(default_factory=list)
    draft_order_edits: list[int] = Field(default_factory=list)


class ReplanRequestIn(BaseModel):
    preview_id: str
    workspace_version: int


class ReplanAcceptedOut(SolveAcceptedOut):
    execution_session_id: int
    active_run_id: int
