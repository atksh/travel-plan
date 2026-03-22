"""Replanning helpers: fix visited prefix, handle in-progress stops, suggest alternatives."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.errors import StateContractError
from app.models.poi import PoiMaster
from app.models.trip import TripCandidate, TripExecutionEvent, TripPlan
from app.services.geo import estimate_drive_minutes
from app.services.routing_costs import build_solve_pipeline, prune_candidates
from app.solver.model import SolverResult

JST = timezone(timedelta(hours=9))


def _current_replan_minute(
    plan_date: date,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now.astimezone(JST) if now is not None else datetime.now(JST)
    days_offset = max(0, (current_time.date() - plan_date).days)
    return days_offset * 24 * 60 + current_time.hour * 60 + current_time.minute


@dataclass
class ReplanContext:
    trip_id: int
    now_minute: int
    current_lat: float | None
    current_lng: float | None
    completed_poi_ids: list[int] = field(default_factory=list)
    skipped_poi_ids: list[int] = field(default_factory=list)
    in_progress_poi_id: int | None = None


@dataclass
class ReplanPreparedState:
    trip: TripPlan
    remaining_candidate_ids: list[int]
    must_visit_ids: set[int]
    excluded_ids: set[int]
    utility_overrides: dict[int, int]
    satisfied_categories: set[str]
    cafe_requirement_already_met: bool
    origin_override: tuple[float, float] | None
    in_progress_poi_id: int | None
    alternative_ids: list[int] = field(default_factory=list)


def load_replan_context(session: Session, trip_id: int) -> ReplanContext:
    trip = session.get(TripPlan, trip_id)
    if trip is None:
        raise ValueError("trip not found")

    completed: list[int] = []
    skipped: list[int] = []
    in_progress: int | None = None
    for event in (
        session.query(TripExecutionEvent)
        .filter(TripExecutionEvent.trip_id == trip_id)
        .order_by(TripExecutionEvent.recorded_at.asc())
    ):
        payload = event.payload_json or {}
        if event.event_type == "arrived":
            in_progress = int(payload.get("poi_id", 0)) or None
        elif event.event_type == "departed":
            if in_progress is not None:
                completed.append(in_progress)
            in_progress = None
        elif event.event_type == "skipped":
            poi_id = int(payload.get("poi_id", 0))
            if poi_id:
                skipped.append(poi_id)
                if in_progress == poi_id:
                    in_progress = None

    return ReplanContext(
        trip_id=trip_id,
        now_minute=_current_replan_minute(trip.plan_date),
        current_lat=None,
        current_lng=None,
        completed_poi_ids=list(dict.fromkeys(completed)),
        skipped_poi_ids=list(dict.fromkeys(skipped)),
        in_progress_poi_id=in_progress,
    )


def prepare_replan_state(session: Session, ctx: ReplanContext) -> ReplanPreparedState:
    trip = session.get(TripPlan, ctx.trip_id)
    if trip is None:
        raise ValueError("trip not found")

    candidates = (
        session.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip.id, TripCandidate.status == "active")
        .all()
    )
    excluded_ids = {
        candidate.poi_id
        for candidate in candidates
        if candidate.excluded or candidate.locked_out
    }
    utility_overrides = {
        candidate.poi_id: candidate.utility_override
        for candidate in candidates
        if candidate.utility_override is not None
    }
    remaining_candidate_ids = [
        candidate.poi_id
        for candidate in candidates
        if not candidate.excluded and not candidate.locked_out
    ]
    must_visit_ids = {
        candidate.poi_id
        for candidate in candidates
        if candidate.must_visit or candidate.locked_in
    }

    excluded_for_replan = list(
        dict.fromkeys(
            ctx.completed_poi_ids
            + ctx.skipped_poi_ids
            + ([ctx.in_progress_poi_id] if ctx.in_progress_poi_id is not None else [])
        )
    )
    for poi_id in excluded_for_replan:
        if poi_id in remaining_candidate_ids:
            remaining_candidate_ids.remove(poi_id)
        excluded_ids.add(poi_id)
        must_visit_ids.discard(poi_id)

    satisfied_poi_ids = list(dict.fromkeys(ctx.completed_poi_ids))
    if ctx.in_progress_poi_id is not None:
        satisfied_poi_ids.append(ctx.in_progress_poi_id)
    satisfied_categories: set[str] = set()
    cafe_requirement_already_met = False
    if satisfied_poi_ids:
        satisfied_pois = (
            session.query(PoiMaster)
            .filter(PoiMaster.id.in_(satisfied_poi_ids))
            .all()
        )
        satisfied_categories = {
            poi.primary_category for poi in satisfied_pois if poi.primary_category
        }
        cafe_requirement_already_met = any(
            any(link.tag.slug == "cafe" for link in poi.tag_links)
            for poi in satisfied_pois
        )

    pruned = prune_candidates(
        candidate_poi_ids=remaining_candidate_ids,
        must_visit=must_visit_ids,
        excluded=excluded_ids,
        plan_date=trip.plan_date,
        weather_mode=trip.weather_mode,
        session=session,
    )

    origin_override: tuple[float, float] | None = None
    if ctx.current_lat is not None and ctx.current_lng is not None:
        origin_override = (ctx.current_lat, ctx.current_lng)
    elif ctx.in_progress_poi_id is not None:
        current_poi = session.get(PoiMaster, ctx.in_progress_poi_id)
        if current_poi is not None:
            origin_override = (current_poi.lat, current_poi.lng)

    return ReplanPreparedState(
        trip=trip,
        remaining_candidate_ids=pruned,
        must_visit_ids=must_visit_ids,
        excluded_ids=excluded_ids,
        utility_overrides=utility_overrides,
        satisfied_categories=satisfied_categories,
        cafe_requirement_already_met=cafe_requirement_already_met,
        origin_override=origin_override,
        in_progress_poi_id=ctx.in_progress_poi_id,
    )


def find_alternative_poi_ids(
    session: Session,
    failed_poi_id: int,
    candidate_ids: list[int],
    *,
    weather_mode: str,
    limit: int = 3,
) -> list[int]:
    failed_poi = session.get(PoiMaster, failed_poi_id)
    if failed_poi is None:
        return []
    candidate_pois = (
        session.query(PoiMaster).filter(PoiMaster.id.in_(candidate_ids)).all()
    )
    ranked: list[tuple[tuple[int, int], int]] = []
    for poi in candidate_pois:
        if poi.id == failed_poi_id:
            continue
        is_indoor = bool(poi.planning_profile and poi.planning_profile.is_indoor)
        if weather_mode == "rain" and not is_indoor:
            continue
        same_category = 0 if poi.primary_category == failed_poi.primary_category else 1
        drive_minutes = estimate_drive_minutes(
            failed_poi.lat, failed_poi.lng, poi.lat, poi.lng
        )
        ranked.append(((same_category, drive_minutes), poi.id))
    ranked.sort(key=lambda item: item[0])
    return [poi_id for _rank, poi_id in ranked[:limit]]


def annotate_must_visit_failure(
    session: Session,
    result: SolverResult,
    state: ReplanPreparedState,
    *,
    now_minute: int,
) -> ReplanPreparedState:
    if result.feasible or not state.must_visit_ids:
        return state

    alternative_ids: list[int] = []
    for poi_id in sorted(state.must_visit_ids):
        code = f"must_visit_{poi_id}_infeasible_after_{now_minute:04d}"
        if code not in result.reason_codes:
            result.reason_codes.append(code)
        alternative_ids.extend(
            find_alternative_poi_ids(
                session,
                poi_id,
                state.remaining_candidate_ids,
                weather_mode=state.trip.weather_mode,
            )
        )
    state.alternative_ids = list(dict.fromkeys(alternative_ids))
    return state


def replan_trip(session: Session, ctx: ReplanContext) -> SolverResult:
    state = prepare_replan_state(session, ctx)
    pref = state.trip.preference_profile
    if pref is None:
        raise StateContractError(
            "TRIP_PREFERENCE_PROFILE_MISSING",
            "Trip is missing a preference profile.",
            details={"trip_id": state.trip.id},
        )
    pipeline = asyncio.run(
        build_solve_pipeline(
            session,
            state.trip,
            use_traffic_matrix=False,
            origin_override=state.origin_override,
            departure_start_min=ctx.now_minute,
            departure_window_end_min=ctx.now_minute,
            candidate_ids=state.remaining_candidate_ids,
            must_visit=state.must_visit_ids,
            excluded_ids=state.excluded_ids,
            utility_overrides=state.utility_overrides,
            max_continuous_drive_minutes=pref.max_continuous_drive_minutes,
            satisfied_categories=state.satisfied_categories,
            cafe_requirement_already_met=state.cafe_requirement_already_met,
        )
    )
    result = pipeline.solver_result
    annotate_must_visit_failure(session, result, state, now_minute=ctx.now_minute)
    return result
