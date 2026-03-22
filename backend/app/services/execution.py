from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.errors import RequestContractError
from app.models.execution import ExecutionEvent, ExecutionSession
from app.models.solve import SolveRouteLeg, SolveRun, SolveStop
from app.models.trip import Trip
from app.services.workspace import serialize_solve_run, serialize_trip_detail


def get_execution_session_or_error(session: Session, trip_id: int) -> ExecutionSession:
    execution_session = (
        session.query(ExecutionSession)
        .filter(ExecutionSession.trip_id == trip_id)
        .one_or_none()
    )
    if execution_session is None:
        raise RequestContractError(
            "EXECUTION_NOT_STARTED",
            "Execution has not been started for this trip.",
            status_code=409,
        )
    return execution_session


def append_execution_event(
    session: Session,
    *,
    trip_id: int,
    execution_session_id: int | None,
    event_type: str,
    payload: dict,
) -> ExecutionEvent:
    event = ExecutionEvent(
        trip_id=trip_id,
        execution_session_id=execution_session_id,
        event_type=event_type,
        payload_json=payload,
        recorded_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.flush()
    return event


def _current_and_next_stop(stops: list[dict], events: list[ExecutionEvent]) -> tuple[dict | None, dict | None]:
    completed_place_ids: list[int] = []
    in_progress_place_id: int | None = None
    for event in events:
        place_id = event.payload_json.get("place_id")
        if event.event_type == "arrived" and isinstance(place_id, int):
            in_progress_place_id = place_id
        elif event.event_type == "departed" and in_progress_place_id is not None:
            completed_place_ids.append(in_progress_place_id)
            in_progress_place_id = None
        elif event.event_type == "skipped" and isinstance(place_id, int):
            completed_place_ids.append(place_id)
            if in_progress_place_id == place_id:
                in_progress_place_id = None
    place_stops = [stop for stop in stops if stop["place_id"] is not None]
    current_stop = None
    next_stop = None
    if in_progress_place_id is not None:
        current_stop = next((stop for stop in place_stops if stop["place_id"] == in_progress_place_id), None)
        if current_stop is not None:
            current_index = place_stops.index(current_stop)
            next_stop = place_stops[current_index + 1] if current_index + 1 < len(place_stops) else None
    else:
        current_stop = next(
            (stop for stop in place_stops if stop["place_id"] not in completed_place_ids),
            None,
        )
        if current_stop is not None:
            current_index = place_stops.index(current_stop)
            next_stop = place_stops[current_index + 1] if current_index + 1 < len(place_stops) else None
    return current_stop, next_stop


def build_execution_bootstrap(session: Session, trip: Trip) -> dict:
    execution_session = get_execution_session_or_error(session, trip.id)
    if execution_session.active_run_id is None:
        raise RequestContractError(
            "REPLAN_NOT_ALLOWED",
            "Execution has no active solve run.",
            status_code=409,
        )
    run = session.get(SolveRun, execution_session.active_run_id)
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
    events = (
        session.query(ExecutionEvent)
        .filter(ExecutionEvent.trip_id == trip.id)
        .order_by(ExecutionEvent.recorded_at.asc())
        .all()
    )
    solve_payload = serialize_solve_run(run, stops=stops, route_legs=route_legs)
    current_stop, next_stop = _current_and_next_stop(solve_payload["stops"], events)
    return {
        "trip": serialize_trip_detail(trip),
        "execution_session": {
            "execution_session_id": execution_session.id,
            "active_run_id": execution_session.active_run_id,
            "status": execution_session.status,
            "started_at": None if execution_session.started_at is None else execution_session.started_at.isoformat(),
            "completed_at": None if execution_session.completed_at is None else execution_session.completed_at.isoformat(),
            "current_stop_id": execution_session.current_stop_sequence_order,
        },
        "active_solve": solve_payload,
        "events": [
            {
                "event_id": event.id,
                "event_type": event.event_type,
                "payload": dict(event.payload_json or {}),
                "recorded_at": event.recorded_at.isoformat(),
            }
            for event in events
        ],
        "current_stop": current_stop,
        "next_stop": next_stop,
        "replan_readiness": {
            "can_replan": True,
            "reasons": [],
        },
    }
