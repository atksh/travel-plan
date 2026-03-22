import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.seed import (
    DEFAULT_MUST_VISIT_SEED_KEYS,
    TRIP_CANDIDATE_SEED_KEYS,
    resolve_seed_poi_ids,
)
from app.models.poi import PoiMaster
from app.models.trip import (
    PlannedStop,
    SolverRun,
    TripCandidate,
    TripExecutionEvent,
    TripPlan,
    TripPreferenceProfile,
)
from app.schemas.trip import (
    CandidateCreate,
    CandidateOut,
    CandidatePatch,
    EventCreate,
    EventOut,
    PlannedStopOut,
    ReplanRequest,
    RoutePreviewOut,
    SolveRequest,
    SolveResponse,
    SolverRunOut,
    TripCreate,
    TripDetailOut,
    TripPatch,
    TripPreferenceOut,
    TripPreferencePatch,
)
from app.services.routing_costs import build_solve_pipeline
from app.solver.model import SolverResult
from app.solver.replanner import (
    ReplanContext,
    annotate_must_visit_failure,
    load_replan_context,
    prepare_replan_state,
)

router = APIRouter(prefix="/trips", tags=["trips"])

DUPLICATE_CANDIDATE_DETAIL = "Candidate already exists for this POI"
INTERNAL_TRIP_POI_CATEGORIES = frozenset({"start", "end"})


def _get_trip_or_404(db: Session, trip_id: int) -> TripPlan:
    trip = db.get(TripPlan, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


def _default_preference_values() -> dict[str, Any]:
    return {
        "driving_penalty_weight": 0.05,
        "max_continuous_drive_minutes": 120,
        "preferred_lunch_tags": [],
        "preferred_dinner_tags": [],
        "must_have_cafe": False,
        "budget_band": None,
        "pace_style": "balanced",
    }


def _merged_preference_values(
    body: TripPreferencePatch | None,
) -> dict[str, Any]:
    return _default_preference_values() | (
        body.model_dump(exclude_unset=True) if body is not None else {}
    )


def _preference_fields(pref: TripPreferenceProfile | None) -> dict[str, Any]:
    if pref is None:
        return _default_preference_values()
    return {
        "driving_penalty_weight": pref.driving_penalty_weight,
        "max_continuous_drive_minutes": pref.max_continuous_drive_minutes,
        "preferred_lunch_tags": list(pref.preferred_lunch_tags or []),
        "preferred_dinner_tags": list(pref.preferred_dinner_tags or []),
        "must_have_cafe": pref.must_have_cafe,
        "budget_band": pref.budget_band,
        "pace_style": pref.pace_style,
    }


def _serialize_preference(
    pref: TripPreferenceProfile | None,
) -> TripPreferenceOut | None:
    return None if pref is None else TripPreferenceOut(**_preference_fields(pref))


def _serialize_candidate(candidate: TripCandidate) -> CandidateOut:
    poi = candidate.poi
    return CandidateOut(
        id=candidate.id,
        poi_id=candidate.poi_id,
        poi_name=poi.name if poi is not None else f"POI {candidate.poi_id}",
        primary_category=poi.primary_category if poi is not None else "unknown",
        status=candidate.status,
        source=candidate.source,
        must_visit=candidate.must_visit,
        excluded=candidate.excluded,
        locked_in=candidate.locked_in,
        locked_out=candidate.locked_out,
        user_note=candidate.user_note,
        utility_override=candidate.utility_override,
        candidate_rank=candidate.candidate_rank,
    )


def _serialize_planned_stop(
    stop: PlannedStop,
    *,
    start_label: str | None = None,
    start_lat: float | None = None,
    start_lng: float | None = None,
    end_label: str | None = None,
    end_lat: float | None = None,
    end_lng: float | None = None,
) -> PlannedStopOut:
    if stop.node_kind == "start":
        label = stop.label or start_label
        lat = stop.lat if stop.lat is not None else start_lat
        lng = stop.lng if stop.lng is not None else start_lng
    elif stop.node_kind == "end":
        label = stop.label or end_label
        lat = stop.lat if stop.lat is not None else end_lat
        lng = stop.lng if stop.lng is not None else end_lng
    else:
        label = stop.label or (stop.poi.name if stop.poi is not None else None)
        lat = stop.lat if stop.lat is not None else (
            stop.poi.lat if stop.poi is not None else None
        )
        lng = stop.lng if stop.lng is not None else (
            stop.poi.lng if stop.poi is not None else None
        )
    return PlannedStopOut(
        id=stop.id,
        sequence_order=stop.sequence_order,
        poi_id=stop.poi_id,
        poi_name=label,
        label=label,
        node_kind=stop.node_kind,
        lat=lat,
        lng=lng,
        arrival_min=stop.arrival_min,
        departure_min=stop.departure_min,
        stay_min=stop.stay_min,
        leg_from_prev_min=stop.leg_from_prev_min,
        status=stop.status,
    )


def _planned_stop(
    *,
    sequence_order: int,
    poi_id: int | None,
    poi_name: str | None,
    label: str | None,
    node_kind: str,
    lat: float | None,
    lng: float | None,
    arrival_min: int | None,
    departure_min: int | None,
    stay_min: int | None,
    leg_from_prev_min: int | None,
) -> PlannedStopOut:
    return PlannedStopOut(
        sequence_order=sequence_order,
        poi_id=poi_id,
        poi_name=poi_name,
        label=label,
        node_kind=node_kind,
        lat=lat,
        lng=lng,
        arrival_min=arrival_min,
        departure_min=departure_min,
        stay_min=stay_min,
        leg_from_prev_min=leg_from_prev_min,
        status="planned",
    )


def _build_transient_planned_stops(
    db: Session,
    trip: TripPlan,
    result: SolverResult,
    *,
    start_label: str | None = None,
    start_lat: float | None = None,
    start_lng: float | None = None,
    end_label: str | None = None,
    end_lat: float | None = None,
    end_lng: float | None = None,
) -> list[PlannedStopOut]:
    if not result.feasible:
        return []

    start_label = start_label or trip.origin_label
    start_lat = trip.origin_lat if start_lat is None else start_lat
    start_lng = trip.origin_lng if start_lng is None else start_lng
    end_label = end_label or trip.dest_label
    end_lat = trip.dest_lat if end_lat is None else end_lat
    end_lng = trip.dest_lng if end_lng is None else end_lng
    start_departure_min = result.start_departure_min or trip.departure_window_start_min
    poi_map = {
        poi.id: poi
        for poi in db.query(PoiMaster).filter(PoiMaster.id.in_(result.ordered_poi_ids)).all()
    }
    stops = [
        _planned_stop(
            sequence_order=0,
            poi_id=None,
            poi_name=start_label,
            label=start_label,
            node_kind="start",
            lat=start_lat,
            lng=start_lng,
            arrival_min=start_departure_min,
            departure_min=start_departure_min,
            stay_min=0,
            leg_from_prev_min=None,
        )
    ]

    for index, poi_id in enumerate(result.ordered_poi_ids, start=1):
        arrival = result.arrival_minutes[index - 1] if index - 1 < len(result.arrival_minutes) else None
        departure = (
            result.departure_minutes[index - 1]
            if index - 1 < len(result.departure_minutes)
            else None
        )
        poi = poi_map.get(poi_id)
        label = poi.name if poi is not None else f"POI {poi_id}"
        stops.append(
            _planned_stop(
                sequence_order=index,
                poi_id=poi_id,
                poi_name=label,
                label=label,
                node_kind="poi",
                lat=poi.lat if poi is not None else None,
                lng=poi.lng if poi is not None else None,
                arrival_min=arrival,
                departure_min=departure,
                stay_min=(
                    departure - arrival
                    if arrival is not None and departure is not None
                    else None
                ),
                leg_from_prev_min=(
                    result.leg_minutes[index - 1]
                    if index - 1 < len(result.leg_minutes)
                    else None
                ),
            )
        )

    end_index = len(result.ordered_poi_ids) + 1
    end_arrival = (
        result.arrival_minutes[len(result.ordered_poi_ids)]
        if len(result.arrival_minutes) > len(result.ordered_poi_ids)
        else trip.return_deadline_min
    )
    stops.append(
        _planned_stop(
            sequence_order=end_index,
            poi_id=None,
            poi_name=end_label,
            label=end_label,
            node_kind="end",
            lat=end_lat,
            lng=end_lng,
            arrival_min=end_arrival,
            departure_min=end_arrival,
            stay_min=0,
            leg_from_prev_min=result.leg_minutes[-1] if result.leg_minutes else None,
        )
    )
    return stops


def _get_latest_route(db: Session, trip_id: int) -> tuple[SolverRun | None, list[PlannedStopOut]]:
    run = (
        db.query(SolverRun)
        .filter(SolverRun.trip_id == trip_id)
        .order_by(SolverRun.id.desc())
        .first()
    )
    if run is None:
        return None, []
    trip = run.trip
    stops = (
        db.query(PlannedStop)
        .filter(PlannedStop.solver_run_id == run.id)
        .order_by(PlannedStop.sequence_order)
        .all()
    )
    return run, [
        _serialize_planned_stop(
            stop,
            start_label=trip.origin_label if trip is not None else None,
            start_lat=trip.origin_lat if trip is not None else None,
            start_lng=trip.origin_lng if trip is not None else None,
            end_label=trip.dest_label if trip is not None else None,
            end_lat=trip.dest_lat if trip is not None else None,
            end_lng=trip.dest_lng if trip is not None else None,
        )
        for stop in stops
    ]


def _serialize_trip_detail(db: Session, trip: TripPlan) -> TripDetailOut:
    candidates = (
        db.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip.id)
        .order_by(TripCandidate.id.asc())
        .all()
    )
    latest_run, latest_route = _get_latest_route(db, trip.id)
    return TripDetailOut(
        id=trip.id,
        state=trip.state,
        plan_date=trip.plan_date,
        origin_lat=trip.origin_lat,
        origin_lng=trip.origin_lng,
        origin_label=trip.origin_label,
        dest_lat=trip.dest_lat,
        dest_lng=trip.dest_lng,
        dest_label=trip.dest_label,
        departure_window_start_min=trip.departure_window_start_min,
        departure_window_end_min=trip.departure_window_end_min,
        return_deadline_min=trip.return_deadline_min,
        weather_mode=trip.weather_mode,
        preference_profile=_serialize_preference(trip.preference_profile),
        candidates=[_serialize_candidate(candidate) for candidate in candidates],
        latest_route=latest_route,
        latest_solver_run=(
            SolverRunOut.model_validate(latest_run) if latest_run is not None else None
        ),
    )


def _ordered_unique_poi_ids(poi_ids: list[int] | None) -> list[int]:
    return list(dict.fromkeys(poi_ids or []))


def _load_poi_categories(db: Session, poi_ids: list[int]) -> dict[int, str]:
    if not poi_ids:
        return {}
    return {
        poi_id: category
        for poi_id, category in (
            db.query(PoiMaster.id, PoiMaster.primary_category)
            .filter(PoiMaster.id.in_(poi_ids))
            .all()
        )
    }


def _validate_trip_selectable_poi_ids(db: Session, poi_ids: list[int]) -> None:
    categories = _load_poi_categories(db, _ordered_unique_poi_ids(poi_ids))
    for poi_id in _ordered_unique_poi_ids(poi_ids):
        category = categories.get(poi_id)
        if category is None:
            raise HTTPException(status_code=404, detail=f"POI not found: {poi_id}")
        if category in INTERNAL_TRIP_POI_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"POI cannot be selected for trips: {poi_id}",
            )


def _get_trip_selectable_poi_or_error(db: Session, poi_id: int) -> PoiMaster:
    poi = db.get(PoiMaster, poi_id)
    if poi is None:
        raise HTTPException(status_code=404, detail="POI not found")
    if poi.primary_category in INTERNAL_TRIP_POI_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"POI cannot be selected for trips: {poi_id}",
        )
    return poi


def _is_duplicate_trip_candidate_error(exc: IntegrityError) -> bool:
    message = str(exc.orig).lower()
    return "uq_trip_candidate_trip_id_poi_id" in message or (
        "trip_candidate.trip_id" in message and "trip_candidate.poi_id" in message
    )


def _resolve_replan_start_metadata(
    db: Session,
    trip: TripPlan,
    ctx: ReplanContext,
) -> tuple[str, float, float]:
    if ctx.current_lat is not None and ctx.current_lng is not None:
        return "Current location", ctx.current_lat, ctx.current_lng
    if ctx.in_progress_poi_id is not None:
        current_poi = db.get(PoiMaster, ctx.in_progress_poi_id)
        if current_poi is not None:
            return current_poi.name, current_poi.lat, current_poi.lng
    return trip.origin_label, trip.origin_lat, trip.origin_lng


def _resolve_initial_candidate_state(
    db: Session,
    body: TripCreate,
) -> tuple[list[int], set[int], set[int]]:
    must_visit_ids = _ordered_unique_poi_ids(body.initial_must_visit_poi_ids)
    excluded_ids = _ordered_unique_poi_ids(body.initial_excluded_poi_ids)
    overlap = set(must_visit_ids) & set(excluded_ids)
    if overlap:
        raise HTTPException(
            status_code=400,
            detail="POIs cannot be both must-visit and excluded",
        )

    explicit_candidate_ids = must_visit_ids + [
        poi_id for poi_id in excluded_ids if poi_id not in must_visit_ids
    ]
    _validate_trip_selectable_poi_ids(db, explicit_candidate_ids)

    candidate_ids = list(
        resolve_seed_poi_ids(db, TRIP_CANDIDATE_SEED_KEYS, trip_selectable_only=True)
    )
    candidate_ids.extend(
        poi_id for poi_id in explicit_candidate_ids if poi_id not in candidate_ids
    )
    excluded = {poi_id for poi_id in excluded_ids if poi_id in candidate_ids}
    if body.initial_must_visit_poi_ids is None:
        must_visit = set(resolve_seed_poi_ids(db, DEFAULT_MUST_VISIT_SEED_KEYS))
        must_visit &= set(candidate_ids)
        must_visit -= excluded
    else:
        must_visit = {poi_id for poi_id in must_visit_ids if poi_id in candidate_ids}
    return candidate_ids, must_visit, excluded


def _candidate_state(candidates: list[TripCandidate]) -> dict[str, Any]:
    return {
        "candidate_ids": [candidate.poi_id for candidate in candidates if not candidate.locked_out],
        "must_visit": {
            candidate.poi_id
            for candidate in candidates
            if candidate.must_visit or candidate.locked_in
        },
        "excluded_ids": {
            candidate.poi_id
            for candidate in candidates
            if candidate.excluded or candidate.locked_out
        },
        "utility_overrides": {
            candidate.poi_id: candidate.utility_override
            for candidate in candidates
            if candidate.utility_override is not None
        },
    }


def _hash_solver_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _append_event(
    db: Session,
    trip_id: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> TripExecutionEvent:
    event = TripExecutionEvent(
        trip_id=trip_id,
        event_type=event_type,
        payload_json=payload,
        recorded_at=datetime.now(timezone.utc),
    )
    db.add(event)
    return event


def _persist_solver_run(
    db: Session,
    *,
    trip_id: int,
    input_hash: str,
    started_at: datetime,
    result: SolverResult,
    summary: dict[str, Any],
) -> SolverRun:
    run = SolverRun(
        trip_id=trip_id,
        input_hash=input_hash,
        solve_started_at=started_at,
        solve_ms=result.solve_ms,
        objective_value=result.objective,
        infeasible_reason=",".join(result.reason_codes) if result.reason_codes else None,
        route_summary_json=summary,
    )
    db.add(run)
    db.flush()
    return run


def _persist_planned_stops(
    db: Session,
    run_id: int,
    planned_stops: list[PlannedStopOut],
) -> None:
    for stop in planned_stops:
        db.add(
            PlannedStop(
                solver_run_id=run_id,
                sequence_order=stop.sequence_order,
                poi_id=stop.poi_id,
                label=stop.label,
                node_kind=stop.node_kind,
                lat=stop.lat,
                lng=stop.lng,
                arrival_min=stop.arrival_min,
                departure_min=stop.departure_min,
                stay_min=stop.stay_min,
                leg_from_prev_min=stop.leg_from_prev_min,
                status=stop.status,
            )
        )


def _solve_response(
    result: SolverResult,
    planned_stops: list[PlannedStopOut],
    *,
    run_id: int,
    alternatives: list[CandidateOut] | None = None,
) -> SolveResponse:
    return SolveResponse(
        feasible=result.feasible,
        objective=result.objective,
        ordered_poi_ids=result.ordered_poi_ids,
        reason_codes=result.reason_codes,
        solve_ms=result.solve_ms,
        planned_stops=planned_stops,
        solver_run_id=run_id,
        alternatives=alternatives or [],
    )


@router.post("", response_model=TripDetailOut)
def create_trip(body: TripCreate, db: Session = Depends(get_db)) -> TripDetailOut:
    candidate_ids, must_visit_ids, excluded_ids = _resolve_initial_candidate_state(db, body)
    default_seed_candidate_ids = set(
        resolve_seed_poi_ids(db, TRIP_CANDIDATE_SEED_KEYS, trip_selectable_only=True)
    )
    trip = TripPlan(
        state="draft",
        plan_date=body.plan_date,
        origin_lat=body.origin_lat,
        origin_lng=body.origin_lng,
        origin_label=body.origin_label,
        dest_lat=body.dest_lat,
        dest_lng=body.dest_lng,
        dest_label=body.dest_label,
        departure_window_start_min=body.departure_window_start_min,
        departure_window_end_min=body.departure_window_end_min,
        return_deadline_min=body.return_deadline_min,
        weather_mode=body.weather_mode,
    )
    db.add(trip)
    db.flush()
    db.add(TripPreferenceProfile(trip_id=trip.id, **_merged_preference_values(body.preferences)))
    for poi_id in candidate_ids:
        db.add(
            TripCandidate(
                trip_id=trip.id,
                poi_id=poi_id,
                status="active",
                source="seed" if poi_id in default_seed_candidate_ids else "user",
                excluded=poi_id in excluded_ids,
                must_visit=poi_id in must_visit_ids,
            )
        )
    db.commit()
    db.refresh(trip)
    return _serialize_trip_detail(db, trip)


@router.get("/{trip_id}", response_model=TripDetailOut)
def get_trip(trip_id: int, db: Session = Depends(get_db)) -> TripDetailOut:
    return _serialize_trip_detail(db, _get_trip_or_404(db, trip_id))


@router.patch("/{trip_id}", response_model=TripDetailOut)
def patch_trip(
    trip_id: int, body: TripPatch, db: Session = Depends(get_db)
) -> TripDetailOut:
    trip = _get_trip_or_404(db, trip_id)
    if body.state is not None:
        trip.state = body.state
    if body.weather_mode is not None:
        if trip.weather_mode != body.weather_mode:
            _append_event(db, trip_id, "weather_changed", {"weather_mode": body.weather_mode})
        trip.weather_mode = body.weather_mode
    db.commit()
    db.refresh(trip)
    return _serialize_trip_detail(db, trip)


@router.patch("/{trip_id}/preferences", response_model=TripDetailOut)
def patch_preferences(
    trip_id: int, body: TripPreferencePatch, db: Session = Depends(get_db)
) -> TripDetailOut:
    trip = _get_trip_or_404(db, trip_id)
    pref = trip.preference_profile
    if pref is None:
        raise HTTPException(status_code=400, detail="No preference profile")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(pref, key, value)
    db.commit()
    db.refresh(trip)
    return _serialize_trip_detail(db, trip)


@router.get("/{trip_id}/candidates", response_model=list[CandidateOut])
def list_candidates(trip_id: int, db: Session = Depends(get_db)) -> list[CandidateOut]:
    _get_trip_or_404(db, trip_id)
    candidates = (
        db.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip_id)
        .order_by(TripCandidate.id.asc())
        .all()
    )
    return [_serialize_candidate(candidate) for candidate in candidates]


@router.post("/{trip_id}/candidates", response_model=CandidateOut)
def add_candidate(
    trip_id: int, body: CandidateCreate, db: Session = Depends(get_db)
) -> CandidateOut:
    _get_trip_or_404(db, trip_id)
    _get_trip_selectable_poi_or_error(db, body.poi_id)
    existing_candidate = (
        db.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip_id, TripCandidate.poi_id == body.poi_id)
        .first()
    )
    if existing_candidate is not None:
        raise HTTPException(status_code=409, detail=DUPLICATE_CANDIDATE_DETAIL)
    candidate = TripCandidate(
        trip_id=trip_id,
        poi_id=body.poi_id,
        status="active",
        source="user",
        must_visit=body.must_visit,
        excluded=body.excluded,
        user_note=body.user_note,
    )
    db.add(candidate)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_trip_candidate_error(exc):
            raise HTTPException(status_code=409, detail=DUPLICATE_CANDIDATE_DETAIL) from exc
        raise
    db.refresh(candidate)
    return _serialize_candidate(candidate)


@router.patch("/{trip_id}/candidates/{candidate_id}", response_model=CandidateOut)
def patch_candidate(
    trip_id: int,
    candidate_id: int,
    body: CandidatePatch,
    db: Session = Depends(get_db),
) -> CandidateOut:
    candidate = db.get(TripCandidate, candidate_id)
    if candidate is None or candidate.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(candidate, key, value)
    db.commit()
    db.refresh(candidate)
    return _serialize_candidate(candidate)


@router.delete("/{trip_id}/candidates/{candidate_id}")
def delete_candidate(
    trip_id: int, candidate_id: int, db: Session = Depends(get_db)
) -> dict[str, bool]:
    candidate = db.get(TripCandidate, candidate_id)
    if candidate is None or candidate.trip_id != trip_id:
        raise HTTPException(status_code=404, detail="Candidate not found")
    db.delete(candidate)
    db.commit()
    return {"ok": True}


@router.post("/{trip_id}/events")
def post_event(
    trip_id: int, body: EventCreate, db: Session = Depends(get_db)
) -> dict[str, Any]:
    _get_trip_or_404(db, trip_id)
    event = _append_event(db, trip_id, body.event_type, body.payload or {})
    db.commit()
    db.refresh(event)
    return {"id": event.id, "event_type": event.event_type}


@router.get("/{trip_id}/events", response_model=list[EventOut])
def list_events(trip_id: int, db: Session = Depends(get_db)) -> list[TripExecutionEvent]:
    _get_trip_or_404(db, trip_id)
    return (
        db.query(TripExecutionEvent)
        .filter(TripExecutionEvent.trip_id == trip_id)
        .order_by(TripExecutionEvent.recorded_at.asc())
        .all()
    )


@router.post("/{trip_id}/solve", response_model=SolveResponse)
async def solve_endpoint(
    trip_id: int, body: SolveRequest, db: Session = Depends(get_db)
) -> SolveResponse:
    trip = _get_trip_or_404(db, trip_id)
    pref = trip.preference_profile
    candidates = (
        db.query(TripCandidate)
        .filter(
            TripCandidate.trip_id == trip_id,
            TripCandidate.status == "active",
            TripCandidate.excluded.is_(False),
        )
        .all()
    )
    state = _candidate_state(candidates)
    pref_values = _preference_fields(pref)
    pipeline = await build_solve_pipeline(
        db,
        trip,
        use_traffic_matrix=body.use_traffic_matrix,
        candidate_ids=state["candidate_ids"],
        must_visit=state["must_visit"],
        excluded_ids=state["excluded_ids"],
        utility_overrides=state["utility_overrides"],
        max_continuous_drive_minutes=pref_values["max_continuous_drive_minutes"],
    )
    result = pipeline.solver_result
    started_at = datetime.now(timezone.utc)
    input_hash = _hash_solver_payload(
        {
            "ids": state["candidate_ids"],
            "must": sorted(state["must_visit"]),
            "dep": trip.departure_window_start_min,
            "dep_end": trip.departure_window_end_min,
            "deadline": trip.return_deadline_min,
            "weather_mode": trip.weather_mode,
            "use_traffic_matrix": body.use_traffic_matrix,
            **pref_values,
        }
    )
    run = _persist_solver_run(
        db,
        trip_id=trip_id,
        input_hash=input_hash,
        started_at=started_at,
        result=result,
        summary={
            "reason_codes": result.reason_codes,
            "feasible": result.feasible,
            "shortlist_ids": pipeline.shortlist_ids,
            "used_bucket": pipeline.used_bucket,
            "used_traffic_matrix": pipeline.used_traffic_matrix,
            "refined_legs": pipeline.refined_legs,
        },
    )
    planned_stops = _build_transient_planned_stops(db, trip, result)
    _persist_planned_stops(db, run.id, planned_stops)
    db.commit()
    return _solve_response(result, planned_stops, run_id=run.id)


@router.post("/{trip_id}/replan", response_model=SolveResponse)
async def replan_endpoint(
    trip_id: int, body: ReplanRequest, db: Session = Depends(get_db)
) -> SolveResponse:
    trip = _get_trip_or_404(db, trip_id)
    ctx = load_replan_context(db, trip_id)
    if body.current_lat is not None and body.current_lng is not None:
        ctx.current_lat = body.current_lat
        ctx.current_lng = body.current_lng
    state = prepare_replan_state(db, ctx)
    pref = state.trip.preference_profile
    pref_values = _preference_fields(pref)
    pipeline = await build_solve_pipeline(
        db,
        state.trip,
        use_traffic_matrix=True,
        origin_override=state.origin_override,
        departure_start_min=ctx.now_minute,
        departure_window_end_min=ctx.now_minute,
        candidate_ids=state.remaining_candidate_ids,
        must_visit=state.must_visit_ids,
        excluded_ids=state.excluded_ids,
        utility_overrides=state.utility_overrides,
        max_continuous_drive_minutes=pref_values["max_continuous_drive_minutes"],
        satisfied_categories=state.satisfied_categories,
        cafe_requirement_already_met=state.cafe_requirement_already_met,
    )
    state = annotate_must_visit_failure(
        db,
        pipeline.solver_result,
        state,
        now_minute=ctx.now_minute,
    )
    result = pipeline.solver_result
    input_hash = _hash_solver_payload(
        {
            "kind": "replan",
            "trip_id": trip_id,
            "candidate_ids": state.remaining_candidate_ids,
            "must_visit": sorted(state.must_visit_ids),
            "completed": ctx.completed_poi_ids,
            "skipped": ctx.skipped_poi_ids,
            "in_progress": ctx.in_progress_poi_id,
            "satisfied_categories": sorted(state.satisfied_categories),
            "cafe_requirement_already_met": state.cafe_requirement_already_met,
            "departure": ctx.now_minute,
            "departure_end": ctx.now_minute,
            "origin_override": state.origin_override,
            "weather_mode": state.trip.weather_mode,
            "preferred_lunch_tags": pref_values["preferred_lunch_tags"],
            "preferred_dinner_tags": pref_values["preferred_dinner_tags"],
            "must_have_cafe": pref_values["must_have_cafe"],
            "budget_band": pref_values["budget_band"],
            "pace_style": pref_values["pace_style"],
        }
    )
    run = _persist_solver_run(
        db,
        trip_id=trip_id,
        input_hash=input_hash,
        started_at=datetime.now(timezone.utc),
        result=result,
        summary={
            "kind": "replan",
            "reason_codes": result.reason_codes,
            "feasible": result.feasible,
            "shortlist_ids": pipeline.shortlist_ids,
            "used_bucket": pipeline.used_bucket,
            "used_traffic_matrix": pipeline.used_traffic_matrix,
        },
    )
    start_label, start_lat, start_lng = _resolve_replan_start_metadata(db, trip, ctx)
    planned_stops = _build_transient_planned_stops(
        db,
        trip,
        result,
        start_label=start_label,
        start_lat=start_lat,
        start_lng=start_lng,
    )
    _persist_planned_stops(db, run.id, planned_stops)
    _append_event(
        db,
        trip_id,
        "replanned",
        {
            "feasible": result.feasible,
            "reason_codes": result.reason_codes,
            "current_lat": ctx.current_lat,
            "current_lng": ctx.current_lng,
            "in_progress_poi_id": ctx.in_progress_poi_id,
        },
    )
    db.commit()
    alternative_candidates = (
        db.query(TripCandidate)
        .filter(
            TripCandidate.trip_id == trip_id,
            TripCandidate.poi_id.in_(state.alternative_ids),
        )
        .all()
        if state.alternative_ids
        else []
    )
    return _solve_response(
        result,
        planned_stops,
        run_id=run.id,
        alternatives=[_serialize_candidate(candidate) for candidate in alternative_candidates],
    )


@router.get("/{trip_id}/route-preview", response_model=RoutePreviewOut)
def route_preview(trip_id: int, db: Session = Depends(get_db)) -> RoutePreviewOut:
    _run, stops = _get_latest_route(db, _get_trip_or_404(db, trip_id).id)
    return RoutePreviewOut(stops=stops)


@router.get("/{trip_id}/solver-runs", response_model=list[SolverRunOut])
def solver_runs(trip_id: int, db: Session = Depends(get_db)) -> list[SolverRunOut]:
    _get_trip_or_404(db, trip_id)
    runs = (
        db.query(SolverRun)
        .filter(SolverRun.trip_id == trip_id)
        .order_by(SolverRun.id.desc())
        .all()
    )
    return [SolverRunOut.model_validate(run) for run in runs]
