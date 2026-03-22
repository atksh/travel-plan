from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.errors import RequestContractError
from app.models.execution import ExecutionSession
from app.models.place import Place
from app.models.rule import TripRule
from app.models.solve import SolvePreview, SolveRouteLeg, SolveRun, SolveStop
from app.models.trip import Trip, TripCandidate
from app.schemas.common import OkResponse
from app.schemas.execution import (
    ExecutionBootstrapOut,
    ExecutionEventCreateIn,
    ExecutionEventOut,
    ExecutionStartOut,
    ReplanAcceptedOut,
    ReplanPreviewRequestIn,
    ReplanRequestIn,
)
from app.schemas.rule import RuleCreateIn, RuleListOut, RuleOut, RulePatchIn
from app.schemas.solve import (
    PreviewOut,
    PreviewRequestIn,
    SolveAcceptedOut,
    SolvePayloadOut,
    SolveRequestIn,
    SolveRunListItemOut,
    SolveRunListOut,
)
from app.schemas.trip import (
    CandidateCreateIn,
    CandidateListOut,
    CandidateOut,
    CandidatePatchIn,
    TripCreateIn,
    TripListOut,
    TripPatchIn,
    TripSummaryOut,
    TripWorkspaceOut,
)
from app.services.execution import append_execution_event, build_execution_bootstrap, get_execution_session_or_error
from app.services.planner import generate_solve_payload, get_trip_or_error, persist_solve_run
from app.services.preview_store import assert_preview_matches_workspace, create_preview, get_preview_or_error
from app.services.rule_validation import validate_rule_payload
from app.services.workspace import (
    increment_workspace_version,
    serialize_candidate,
    serialize_rule,
    serialize_solve_run,
    serialize_workspace,
)

router = APIRouter(prefix="/trips", tags=["trips"])

ALLOWED_PATCH_STATE_TRANSITIONS = {
    ("confirmed", "working"),
    ("completed", "archived"),
}


def _maybe_mark_trip_working(trip: Trip) -> None:
    if trip.state == "draft":
        trip.state = "working"


def _check_workspace_version(trip: Trip, workspace_version: int | None) -> None:
    if workspace_version is None:
        return
    if workspace_version != trip.workspace_version:
        raise RequestContractError(
            "WORKSPACE_VERSION_MISMATCH",
            "The workspace version does not match the current trip state.",
            details={
                "trip_workspace_version": trip.workspace_version,
                "request_workspace_version": workspace_version,
            },
            status_code=409,
        )


def _candidate_or_404(session: Session, trip_id: int, candidate_id: int) -> TripCandidate:
    candidate = session.get(TripCandidate, candidate_id)
    if candidate is None or candidate.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def _rule_or_404(session: Session, trip_id: int, rule_id: int) -> TripRule:
    rule = session.get(TripRule, rule_id)
    if rule is None or rule.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


def _apply_candidate_patch(candidate: TripCandidate, body: CandidatePatchIn) -> None:
    patch = body.model_dump(exclude_unset=True)
    if "candidate_state" in patch:
        candidate.candidate_state = patch["candidate_state"]
    if "priority" in patch:
        candidate.priority = patch["priority"]
    if "locked_in" in patch:
        candidate.locked_in = patch["locked_in"]
    if "locked_out" in patch:
        candidate.locked_out = patch["locked_out"]
    if "utility_override" in patch:
        candidate.utility_override = patch["utility_override"]
    if "manual_order_hint" in patch:
        candidate.manual_order_hint = patch["manual_order_hint"]
    if "user_note" in patch:
        candidate.user_note = patch["user_note"]
    stay_override = patch.get("stay_override")
    if stay_override is not None:
        candidate.stay_override_min = stay_override.get("min")
        candidate.stay_override_preferred = stay_override.get("preferred")
        candidate.stay_override_max = stay_override.get("max")
    time_preference = patch.get("time_preference")
    if time_preference is not None:
        candidate.arrive_after_min = time_preference.get("arrive_after_min")
        candidate.arrive_before_min = time_preference.get("arrive_before_min")
        candidate.depart_after_min = time_preference.get("depart_after_min")
        candidate.depart_before_min = time_preference.get("depart_before_min")


def _current_target_payload(rule: TripRule) -> dict:
    return {
        "kind": rule.target_kind,
        "value": rule.target_payload_json.get("value"),
        "data": {
            key: value
            for key, value in rule.target_payload_json.items()
            if key != "value"
        },
    }


def _apply_rule_patch(rule: TripRule, body: RulePatchIn) -> None:
    patch = body.model_dump(exclude_unset=True)
    if "mode" in patch:
        rule.mode = patch["mode"]
    if "weight" in patch:
        rule.weight = patch["weight"]
    if "operator" in patch:
        rule.operator = patch["operator"]
    if "parameters" in patch:
        rule.parameters_json = dict(patch["parameters"] or {})
    if "carry_forward_strategy" in patch:
        rule.carry_forward_strategy = patch["carry_forward_strategy"]
    if "label" in patch:
        rule.label = patch["label"]
    if "description" in patch:
        rule.description = patch["description"]
    if "target" in patch:
        rule.target_kind = patch["target"].kind
        rule.target_payload_json = {
            "value": patch["target"].value,
            **dict(patch["target"].data or {}),
        }


def _trip_summaries(session: Session) -> list[dict]:
    trips = session.query(Trip).order_by(Trip.plan_date.desc(), Trip.id.desc()).all()
    return [
        {
            "id": trip.id,
            "title": trip.title,
            "plan_date": trip.plan_date,
            "state": trip.state,
            "timezone": trip.timezone,
        }
        for trip in trips
    ]


def _current_minute_for_trip(trip: Trip) -> int:
    now = datetime.now(ZoneInfo(trip.timezone))
    return now.hour * 60 + now.minute


def _active_run_payload(session: Session, run_id: int) -> dict:
    run = session.get(SolveRun, run_id)
    if run is None:
        raise RequestContractError(
            "REPLAN_NOT_ALLOWED",
            "The active solve run could not be found.",
            status_code=409,
        )
    stops = (
        session.query(SolveStop)
        .filter(SolveStop.solve_run_id == run.id)
        .order_by(SolveStop.sequence_order.asc())
        .all()
    )
    route_legs = (
        session.query(SolveRouteLeg)
        .filter(SolveRouteLeg.solve_run_id == run.id)
        .order_by(SolveRouteLeg.from_sequence_order.asc())
        .all()
    )
    return serialize_solve_run(run, stops=stops, route_legs=route_legs)


def _derive_execution_state(events: list[dict]) -> tuple[list[int], int | None, list[int]]:
    completed_place_ids: list[int] = []
    skipped_place_ids: list[int] = []
    in_progress_place_id: int | None = None
    for event in events:
        place_id = event["payload"].get("place_id")
        if event["event_type"] == "arrived" and isinstance(place_id, int):
            in_progress_place_id = place_id
        elif event["event_type"] == "departed" and in_progress_place_id is not None:
            completed_place_ids.append(in_progress_place_id)
            in_progress_place_id = None
        elif event["event_type"] == "skipped" and isinstance(place_id, int):
            skipped_place_ids.append(place_id)
            if in_progress_place_id == place_id:
                in_progress_place_id = None
    return completed_place_ids, in_progress_place_id, skipped_place_ids


def _build_replan_payload(
    *,
    active_solve: dict,
    completed_place_ids: list[int],
    current_label: str,
    suffix_solve: dict,
) -> dict:
    prefix_stops = [active_solve["stops"][0]]
    prefix_stops.extend(
        stop
        for stop in active_solve["stops"]
        if stop["place_id"] in completed_place_ids
    )
    prefix_legs = [
        leg
        for leg in active_solve["route_legs"]
        if leg["to_sequence_order"] <= len(prefix_stops) - 1
    ]
    offset = len(prefix_stops)
    suffix_stops = []
    for stop in suffix_solve["stops"]:
        copied = dict(stop)
        if copied["sequence_order"] == 0:
            copied["sequence_order"] = offset
            copied["status"] = "current"
            copied["label"] = current_label
        else:
            copied["sequence_order"] = copied["sequence_order"] + offset
        suffix_stops.append(copied)
    merged_stops = prefix_stops + suffix_stops
    merged_legs = list(prefix_legs)
    for leg in suffix_solve["route_legs"]:
        merged_legs.append(
            {
                "from_sequence_order": leg["from_sequence_order"] + offset,
                "to_sequence_order": leg["to_sequence_order"] + offset,
                "duration_minutes": leg["duration_minutes"],
                "distance_meters": leg["distance_meters"],
                "encoded_polyline": leg["encoded_polyline"],
            }
        )
    return {
        "summary": {
            "feasible": suffix_solve["summary"]["feasible"],
            "score": suffix_solve["summary"]["score"],
            "total_drive_minutes": active_solve["summary"]["total_drive_minutes"] + suffix_solve["summary"]["total_drive_minutes"],
            "total_stay_minutes": active_solve["summary"]["total_stay_minutes"] + suffix_solve["summary"]["total_stay_minutes"],
            "total_distance_meters": active_solve["summary"]["total_distance_meters"] + suffix_solve["summary"]["total_distance_meters"],
            "start_time_min": merged_stops[0]["departure_min"],
            "end_time_min": merged_stops[-1]["arrival_min"],
        },
        "stops": merged_stops,
        "route_legs": merged_legs,
        "selected_place_ids": list(
            dict.fromkeys(active_solve["selected_place_ids"] + suffix_solve["selected_place_ids"])
        ),
        "unselected_candidates": suffix_solve["unselected_candidates"],
        "rule_results": suffix_solve["rule_results"],
        "warnings": suffix_solve["warnings"],
        "alternatives": suffix_solve["alternatives"],
    }


def _persist_preview_patches_to_workspace(trip: Trip, preview: SolvePreview, session: Session) -> None:
    draft_context = preview.draft_context_json or {}
    for patch in draft_context.get("draft_candidate_patches", []):
        candidate = session.get(TripCandidate, patch.get("candidate_id"))
        if candidate is None or candidate.trip_id != trip.id:
            continue
        _apply_candidate_patch(candidate, CandidatePatchIn.model_validate(patch))
    for patch in draft_context.get("draft_rule_patches", []):
        action = patch.get("action", "update")
        if action == "delete":
            rule = session.get(TripRule, patch.get("rule_id"))
            if rule is not None and rule.trip_id == trip.id:
                session.delete(rule)
            continue
        if action == "create":
            target = patch["target"]
            validate_rule_payload(
                rule_kind=patch["rule_kind"],
                mode=patch["mode"],
                operator=patch["operator"],
                target_kind=target["kind"],
                parameters=patch.get("parameters"),
                weight=patch.get("weight"),
            )
            session.add(
                TripRule(
                    trip_id=trip.id,
                    rule_kind=patch["rule_kind"],
                    scope=patch["scope"],
                    mode=patch["mode"],
                    weight=patch.get("weight"),
                    target_kind=target["kind"],
                    target_payload_json={"value": target.get("value"), **(target.get("data") or {})},
                    operator=patch["operator"],
                    parameters_json=dict(patch.get("parameters") or {}),
                    carry_forward_strategy=patch["carry_forward_strategy"],
                    label=patch["label"],
                    description=patch.get("description"),
                    created_by_surface=patch.get("created_by_surface", "ui"),
                )
            )
            continue
        rule = session.get(TripRule, patch.get("rule_id"))
        if rule is None or rule.trip_id != trip.id:
            continue
        _apply_rule_patch(rule, RulePatchIn.model_validate(patch))
    if draft_context.get("draft_candidate_patches") or draft_context.get("draft_rule_patches"):
        increment_workspace_version(trip)


@router.get("", response_model=TripListOut)
def list_trips(db: Session = Depends(get_db)) -> TripListOut:
    return TripListOut(items=[TripSummaryOut.model_validate(item) for item in _trip_summaries(db)])


@router.post("", response_model=TripWorkspaceOut, status_code=201)
def create_trip(body: TripCreateIn, db: Session = Depends(get_db)) -> TripWorkspaceOut:
    trip = Trip(
        title=body.title,
        plan_date=body.plan_date,
        state="draft",
        timezone=body.timezone,
        origin_label=body.origin.label,
        origin_lat=body.origin.lat,
        origin_lng=body.origin.lng,
        destination_label=body.destination.label,
        destination_lat=body.destination.lat,
        destination_lng=body.destination.lng,
        departure_window_start_min=body.departure_window_start_min,
        departure_window_end_min=body.departure_window_end_min,
        end_constraint_kind=body.end_constraint.kind,
        end_constraint_minute_of_day=body.end_constraint.minute_of_day,
        context_weather=body.context.get("weather"),
        context_traffic_profile=body.context.get("traffic_profile", "default"),
        workspace_version=1,
        accepted_run_id=None,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return TripWorkspaceOut.model_validate(serialize_workspace(db, trip))


@router.get("/{trip_id}", response_model=TripWorkspaceOut)
def get_trip(trip_id: int, db: Session = Depends(get_db)) -> TripWorkspaceOut:
    return TripWorkspaceOut.model_validate(serialize_workspace(db, get_trip_or_error(db, trip_id)))


@router.patch("/{trip_id}", response_model=TripWorkspaceOut)
def patch_trip(trip_id: int, body: TripPatchIn, db: Session = Depends(get_db)) -> TripWorkspaceOut:
    trip = get_trip_or_error(db, trip_id)
    patch = body.model_dump(exclude_unset=True)
    changed = False
    if "state" in patch:
        if (trip.state, patch["state"]) not in ALLOWED_PATCH_STATE_TRANSITIONS:
            raise RequestContractError(
                "RULE_VALIDATION_FAILED",
                "This trip state transition is not allowed.",
                details={"from_state": trip.state, "to_state": patch["state"]},
            )
        trip.state = patch["state"]
        changed = True
    if "title" in patch:
        trip.title = patch["title"]
        changed = True
    if "origin" in patch:
        trip.origin_label = patch["origin"].label
        trip.origin_lat = patch["origin"].lat
        trip.origin_lng = patch["origin"].lng
        changed = True
    if "destination" in patch:
        trip.destination_label = patch["destination"].label
        trip.destination_lat = patch["destination"].lat
        trip.destination_lng = patch["destination"].lng
        changed = True
    if "departure_window_start_min" in patch:
        trip.departure_window_start_min = patch["departure_window_start_min"]
        changed = True
    if "departure_window_end_min" in patch:
        trip.departure_window_end_min = patch["departure_window_end_min"]
        changed = True
    if "end_constraint" in patch:
        trip.end_constraint_kind = patch["end_constraint"].kind
        trip.end_constraint_minute_of_day = patch["end_constraint"].minute_of_day
        changed = True
    if "timezone" in patch:
        trip.timezone = patch["timezone"]
        changed = True
    if "context" in patch:
        trip.context_weather = patch["context"].get("weather")
        trip.context_traffic_profile = patch["context"].get("traffic_profile", "default")
        changed = True
    if changed:
        increment_workspace_version(trip)
        _maybe_mark_trip_working(trip)
    db.commit()
    db.refresh(trip)
    return TripWorkspaceOut.model_validate(serialize_workspace(db, trip))


@router.get("/{trip_id}/candidates", response_model=CandidateListOut)
def list_candidates(trip_id: int, db: Session = Depends(get_db)) -> CandidateListOut:
    trip = get_trip_or_error(db, trip_id)
    return CandidateListOut(items=[CandidateOut.model_validate(serialize_candidate(candidate)) for candidate in trip.candidates])


@router.post("/{trip_id}/candidates", response_model=CandidateOut, status_code=201)
def add_candidate(trip_id: int, body: CandidateCreateIn, db: Session = Depends(get_db)) -> CandidateOut:
    trip = get_trip_or_error(db, trip_id)
    place = db.get(Place, body.place_id)
    if place is None:
        raise RequestContractError("PLACE_NOT_FOUND", "Place not found.", status_code=404)
    duplicate = (
        db.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip.id, TripCandidate.place_id == body.place_id)
        .one_or_none()
    )
    if duplicate is not None:
        raise RequestContractError(
            "RULE_VALIDATION_FAILED",
            "Candidate already exists for this place.",
            status_code=409,
        )
    candidate = TripCandidate(
        trip_id=trip.id,
        place_id=body.place_id,
        candidate_state="active",
        priority=body.priority,
        locked_in=False,
        locked_out=False,
    )
    db.add(candidate)
    increment_workspace_version(trip)
    _maybe_mark_trip_working(trip)
    db.commit()
    db.refresh(candidate)
    return CandidateOut.model_validate(serialize_candidate(candidate))


@router.patch("/{trip_id}/candidates/{candidate_id}", response_model=CandidateOut)
def patch_candidate(
    trip_id: int,
    candidate_id: int,
    body: CandidatePatchIn,
    db: Session = Depends(get_db),
) -> CandidateOut:
    trip = get_trip_or_error(db, trip_id)
    candidate = _candidate_or_404(db, trip_id, candidate_id)
    _apply_candidate_patch(candidate, body)
    increment_workspace_version(trip)
    _maybe_mark_trip_working(trip)
    db.commit()
    db.refresh(candidate)
    return CandidateOut.model_validate(serialize_candidate(candidate))


@router.delete("/{trip_id}/candidates/{candidate_id}", response_model=OkResponse)
def delete_candidate(trip_id: int, candidate_id: int, db: Session = Depends(get_db)) -> OkResponse:
    trip = get_trip_or_error(db, trip_id)
    candidate = _candidate_or_404(db, trip_id, candidate_id)
    db.delete(candidate)
    increment_workspace_version(trip)
    _maybe_mark_trip_working(trip)
    db.commit()
    return OkResponse(ok=True)


@router.get("/{trip_id}/rules", response_model=RuleListOut)
def list_rules(trip_id: int, db: Session = Depends(get_db)) -> RuleListOut:
    trip = get_trip_or_error(db, trip_id)
    return RuleListOut(items=[RuleOut.model_validate(serialize_rule(rule)) for rule in trip.rules])


@router.post("/{trip_id}/rules", response_model=RuleOut, status_code=201)
def create_rule(trip_id: int, body: RuleCreateIn, db: Session = Depends(get_db)) -> RuleOut:
    trip = get_trip_or_error(db, trip_id)
    validate_rule_payload(
        rule_kind=body.rule_kind,
        mode=body.mode,
        operator=body.operator,
        target_kind=body.target.kind,
        parameters=body.parameters,
        weight=body.weight,
    )
    rule = TripRule(
        trip_id=trip.id,
        rule_kind=body.rule_kind,
        scope=body.scope,
        mode=body.mode,
        weight=body.weight,
        target_kind=body.target.kind,
        target_payload_json={"value": body.target.value, **dict(body.target.data or {})},
        operator=body.operator,
        parameters_json=dict(body.parameters or {}),
        carry_forward_strategy=body.carry_forward_strategy,
        label=body.label,
        description=body.description,
        created_by_surface=body.created_by_surface,
    )
    db.add(rule)
    increment_workspace_version(trip)
    _maybe_mark_trip_working(trip)
    db.commit()
    db.refresh(rule)
    return RuleOut.model_validate(serialize_rule(rule))


@router.patch("/{trip_id}/rules/{rule_id}", response_model=RuleOut)
def patch_rule(trip_id: int, rule_id: int, body: RulePatchIn, db: Session = Depends(get_db)) -> RuleOut:
    trip = get_trip_or_error(db, trip_id)
    rule = _rule_or_404(db, trip_id, rule_id)
    target = body.target.model_dump() if body.target is not None else _current_target_payload(rule)
    validate_rule_payload(
        rule_kind=rule.rule_kind,
        mode=body.mode or rule.mode,
        operator=body.operator or rule.operator,
        target_kind=target["kind"],
        parameters=body.parameters if body.parameters is not None else rule.parameters_json,
        weight=body.weight if body.weight is not None else rule.weight,
    )
    _apply_rule_patch(rule, body)
    increment_workspace_version(trip)
    _maybe_mark_trip_working(trip)
    db.commit()
    db.refresh(rule)
    return RuleOut.model_validate(serialize_rule(rule))


@router.delete("/{trip_id}/rules/{rule_id}", response_model=OkResponse)
def delete_rule(trip_id: int, rule_id: int, db: Session = Depends(get_db)) -> OkResponse:
    trip = get_trip_or_error(db, trip_id)
    rule = _rule_or_404(db, trip_id, rule_id)
    db.delete(rule)
    increment_workspace_version(trip)
    _maybe_mark_trip_working(trip)
    db.commit()
    return OkResponse(ok=True)


@router.post("/{trip_id}/preview", response_model=PreviewOut)
async def preview_trip(trip_id: int, body: PreviewRequestIn, db: Session = Depends(get_db)) -> PreviewOut:
    trip = get_trip_or_error(db, trip_id)
    _check_workspace_version(trip, body.workspace_version)
    solve_payload = await generate_solve_payload(
        db,
        trip=trip,
        draft_candidate_patches=body.draft_candidate_patches,
        draft_rule_patches=body.draft_rule_patches,
        draft_order_edits=body.draft_order_edits,
    )
    preview = create_preview(
        db,
        trip=trip,
        preview_kind="planned",
        solve_payload=solve_payload,
        draft_context=body.model_dump(),
    )
    _maybe_mark_trip_working(trip)
    db.commit()
    return PreviewOut.model_validate(
        {
            "preview_id": preview.preview_id,
            "workspace_version": trip.workspace_version,
            "based_on_run_id": trip.accepted_run_id,
            "solve": solve_payload,
        }
    )


@router.post("/{trip_id}/solve", response_model=SolveAcceptedOut)
async def solve_trip_endpoint(trip_id: int, body: SolveRequestIn, db: Session = Depends(get_db)) -> SolveAcceptedOut:
    trip = get_trip_or_error(db, trip_id)
    _check_workspace_version(trip, body.workspace_version)
    if body.preview_id:
        preview = get_preview_or_error(db, body.preview_id)
        assert_preview_matches_workspace(
            trip=trip, preview=preview, workspace_version=body.workspace_version
        )
        solve_payload = dict(preview.solve_json)
        based_on_preview_id = preview.preview_id
    else:
        solve_payload = await generate_solve_payload(db, trip=trip)
        based_on_preview_id = None
    run = persist_solve_run(
        db,
        trip=trip,
        run_kind="planned",
        solve_payload=solve_payload,
        based_on_preview_id=based_on_preview_id,
    )
    trip.accepted_run_id = run.id
    trip.state = "confirmed"
    db.commit()
    return SolveAcceptedOut.model_validate(
        {"solve_run_id": run.id, "accepted": True, "solve": solve_payload}
    )


@router.get("/{trip_id}/solve-runs", response_model=SolveRunListOut)
def list_solve_runs(trip_id: int, db: Session = Depends(get_db)) -> SolveRunListOut:
    get_trip_or_error(db, trip_id)
    runs = (
        db.query(SolveRun)
        .filter(SolveRun.trip_id == trip_id)
        .order_by(SolveRun.id.desc())
        .all()
    )
    return SolveRunListOut(
        items=[
            SolveRunListItemOut.model_validate(
                {
                    "solve_run_id": run.id,
                    "run_kind": run.run_kind,
                    "accepted_at": run.accepted_at.isoformat(),
                    "summary": run.summary_json,
                }
            )
            for run in runs
        ]
    )


@router.get("/{trip_id}/solve-runs/{run_id}", response_model=SolvePayloadOut)
def get_solve_run(trip_id: int, run_id: int, db: Session = Depends(get_db)) -> SolvePayloadOut:
    get_trip_or_error(db, trip_id)
    run = session_run = db.get(SolveRun, run_id)
    if session_run is None or session_run.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Solve run not found")
    stops = (
        db.query(SolveStop)
        .filter(SolveStop.solve_run_id == session_run.id)
        .order_by(SolveStop.sequence_order.asc())
        .all()
    )
    route_legs = (
        db.query(SolveRouteLeg)
        .filter(SolveRouteLeg.solve_run_id == session_run.id)
        .order_by(SolveRouteLeg.from_sequence_order.asc())
        .all()
    )
    return SolvePayloadOut.model_validate(
        serialize_solve_run(run, stops=stops, route_legs=route_legs)
    )


@router.post("/{trip_id}/execution/start", response_model=ExecutionStartOut)
def start_execution(trip_id: int, db: Session = Depends(get_db)) -> ExecutionStartOut:
    trip = get_trip_or_error(db, trip_id)
    if trip.state != "confirmed" or trip.accepted_run_id is None:
        raise RequestContractError(
            "REPLAN_NOT_ALLOWED",
            "Execution can only start from a confirmed trip with an accepted solve.",
            status_code=409,
        )
    execution_session = (
        db.query(ExecutionSession)
        .filter(ExecutionSession.trip_id == trip.id)
        .one_or_none()
    )
    if execution_session is None:
        execution_session = ExecutionSession(
            trip_id=trip.id,
            active_run_id=trip.accepted_run_id,
            status="active",
            started_at=datetime.now(),
            completed_at=None,
            current_stop_sequence_order=None,
            suffix_origin_kind="accepted_run",
            suffix_origin_payload_json={},
        )
        db.add(execution_session)
        db.flush()
    else:
        execution_session.active_run_id = trip.accepted_run_id
        execution_session.status = "active"
        if execution_session.started_at is None:
            execution_session.started_at = datetime.now()
    trip.state = "active"
    db.commit()
    return ExecutionStartOut.model_validate(
        {
            "execution_session_id": execution_session.id,
            "trip_state": trip.state,
            "active_run_id": trip.accepted_run_id,
        }
    )


@router.get("/{trip_id}/execution/bootstrap", response_model=ExecutionBootstrapOut)
def execution_bootstrap(trip_id: int, db: Session = Depends(get_db)) -> ExecutionBootstrapOut:
    trip = get_trip_or_error(db, trip_id)
    return ExecutionBootstrapOut.model_validate(build_execution_bootstrap(db, trip))


@router.post("/{trip_id}/execution/events", response_model=ExecutionEventOut)
def post_execution_event(
    trip_id: int, body: ExecutionEventCreateIn, db: Session = Depends(get_db)
) -> ExecutionEventOut:
    trip = get_trip_or_error(db, trip_id)
    execution_session = get_execution_session_or_error(db, trip.id)
    event = append_execution_event(
        db,
        trip_id=trip.id,
        execution_session_id=execution_session.id,
        event_type=body.event_type,
        payload=dict(body.payload or {}),
    )
    db.commit()
    return ExecutionEventOut.model_validate(
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "payload": dict(event.payload_json or {}),
            "recorded_at": event.recorded_at.isoformat(),
        }
    )


@router.post("/{trip_id}/execution/replan-preview", response_model=PreviewOut)
async def execution_replan_preview(
    trip_id: int, body: ReplanPreviewRequestIn, db: Session = Depends(get_db)
) -> PreviewOut:
    trip = get_trip_or_error(db, trip_id)
    execution_session = get_execution_session_or_error(db, trip.id)
    _check_workspace_version(trip, body.workspace_version)
    if execution_session.active_run_id is None:
        raise RequestContractError(
            "REPLAN_NOT_ALLOWED",
            "Execution has no active run.",
            status_code=409,
        )
    bootstrap = build_execution_bootstrap(db, trip)
    completed_place_ids, in_progress_place_id, skipped_place_ids = _derive_execution_state(
        bootstrap["events"]
    )
    current_context = dict(body.current_context or {})
    if "current_lat" not in current_context or "current_lng" not in current_context:
        if bootstrap["current_stop"] is not None:
            current_context.setdefault("current_lat", bootstrap["current_stop"]["lat"])
            current_context.setdefault("current_lng", bootstrap["current_stop"]["lng"])
            current_context.setdefault("label", "現在地")
    departure_min = int(current_context.get("current_minute") or _current_minute_for_trip(trip))
    draft_candidate_patches = list(body.draft_candidate_patches)
    visited_place_ids = list(
        dict.fromkeys(
            completed_place_ids
            + skipped_place_ids
            + ([in_progress_place_id] if in_progress_place_id is not None else [])
        )
    )
    visited_candidates = (
        db.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip.id, TripCandidate.place_id.in_(visited_place_ids))
        .all()
        if visited_place_ids
        else []
    )
    draft_candidate_patches.extend(
        {
            "candidate_id": candidate.id,
            "candidate_state": "excluded",
            "locked_out": True,
        }
        for candidate in visited_candidates
    )
    suffix_solve = await generate_solve_payload(
        db,
        trip=trip,
        draft_candidate_patches=draft_candidate_patches,
        draft_rule_patches=body.draft_rule_patches,
        draft_order_edits=body.draft_order_edits,
        origin_override={
            "label": current_context.get("label", "現在地"),
            "lat": current_context["current_lat"],
            "lng": current_context["current_lng"],
        },
        departure_override_min=departure_min,
    )
    solve_payload = _build_replan_payload(
        active_solve=_active_run_payload(db, execution_session.active_run_id),
        completed_place_ids=completed_place_ids,
        current_label=current_context.get("label", "現在地"),
        suffix_solve=suffix_solve,
    )
    preview = create_preview(
        db,
        trip=trip,
        preview_kind="replan",
        solve_payload=solve_payload,
        draft_context=body.model_dump(),
    )
    db.commit()
    return PreviewOut.model_validate(
        {
            "preview_id": preview.preview_id,
            "workspace_version": trip.workspace_version,
            "based_on_run_id": execution_session.active_run_id,
            "solve": solve_payload,
        }
    )


@router.post("/{trip_id}/execution/replan", response_model=ReplanAcceptedOut)
def accept_replan(trip_id: int, body: ReplanRequestIn, db: Session = Depends(get_db)) -> ReplanAcceptedOut:
    trip = get_trip_or_error(db, trip_id)
    execution_session = get_execution_session_or_error(db, trip.id)
    preview = get_preview_or_error(db, body.preview_id)
    assert_preview_matches_workspace(trip=trip, preview=preview, workspace_version=body.workspace_version)
    _persist_preview_patches_to_workspace(trip, preview, db)
    run = persist_solve_run(
        db,
        trip=trip,
        run_kind="replan",
        solve_payload=dict(preview.solve_json),
        based_on_preview_id=preview.preview_id,
    )
    trip.accepted_run_id = run.id
    execution_session.active_run_id = run.id
    append_execution_event(
        db,
        trip_id=trip.id,
        execution_session_id=execution_session.id,
        event_type="replanned",
        payload={"preview_id": preview.preview_id, "active_run_id": run.id},
    )
    db.commit()
    return ReplanAcceptedOut.model_validate(
        {
            "execution_session_id": execution_session.id,
            "active_run_id": run.id,
            "solve_run_id": run.id,
            "accepted": True,
            "solve": dict(preview.solve_json),
        }
    )
