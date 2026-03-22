"""Routing cost service with shortlist, cache, matrix calls, and leg refinement."""

from __future__ import annotations

import hashlib
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.config import settings
from app.models.poi import PoiMaster
from app.models.routing_cache import RoutingCacheEntry, RoutingRequestLog
from app.models.trip import TripCandidate, TripPlan
from app.services.geo import estimate_drive_minutes
from app.services.google_places import compute_route_matrix_minutes
from app.solver.model import SolverInput, SolverResult, pace_shortlist_max, solve_trip
from app.solver.refine import LegRefinement, refine_legs

DEFAULT_SHORTLIST_MAX = 15
ROUTE_MATRIX_COST_PER_ELEMENT_USD = 0.005
JST = timezone(timedelta(hours=9))
DEPARTURE_BUCKETS = ("departure", "late_morning", "afternoon", "sunset", "dinner")
OUTDOOR_RAIN_CATEGORIES = {"sightseeing_active", "sunset"}
TRAFFIC_INTENSIVE_BUCKETS = {"sunset", "dinner"}


@dataclass
class BaselineMatrixResult:
    """Travel time matrix in minutes (integer) and node order."""

    node_ids: list[int]
    matrix: list[list[int]]


@dataclass
class SolvePipelineResult:
    solver_result: SolverResult
    node_ids: list[int]
    matrix: list[list[int]]
    shortlist_ids: list[int]
    refined_legs: list[dict[str, Any]]
    used_bucket: str
    used_traffic_matrix: bool


def _hash_coords(lat: float, lng: float) -> str:
    return hashlib.sha256(f"{lat:.5f},{lng:.5f}".encode()).hexdigest()[:32]


def _minute_to_iso(plan_date: date, minute_of_day: int) -> str:
    days, minute = divmod(minute_of_day, 24 * 60)
    hour, minute = divmod(minute, 60)
    return (
        datetime.combine(plan_date, time(hour=0, minute=0), JST)
        + timedelta(days=days, hours=hour, minutes=minute)
    ).isoformat()


def _bucket_departure_minutes(base_departure_min: int) -> dict[str, int]:
    return {
        "departure": base_departure_min,
        "late_morning": max(base_departure_min + 120, 11 * 60),
        "afternoon": max(base_departure_min + 240, 14 * 60),
        "sunset": max(base_departure_min + 360, 17 * 60),
        "dinner": max(base_departure_min + 420, 18 * 60 + 30),
    }


def _iter_pairs(node_ids: Sequence[int]):
    for i, origin_node in enumerate(node_ids):
        for j, destination_node in enumerate(node_ids):
            if i != j:
                yield i, j, origin_node, destination_node


def _select_bucket_from_result(
    result: SolverResult,
    *,
    departure_min: int,
    category_by_poi_id: dict[int, str],
) -> str:
    if not result.feasible or not result.ordered_poi_ids:
        return "departure"
    ordered_categories = [
        category_by_poi_id.get(poi_id) for poi_id in result.ordered_poi_ids
    ]
    if "dinner" in ordered_categories:
        return "dinner"
    if "sunset" in ordered_categories:
        return "sunset"
    last_departure = departure_min
    last_index = len(result.ordered_poi_ids) - 1
    if 0 <= last_index < len(result.departure_minutes):
        candidate = result.departure_minutes[last_index]
        if candidate is not None:
            last_departure = candidate
    if last_departure >= 14 * 60:
        return "afternoon"
    if last_departure >= 11 * 60:
        return "late_morning"
    return "departure"


def _is_weather_blocked(poi: PoiMaster, weather_mode: str) -> bool:
    profile = poi.planning_profile
    return (
        weather_mode == "rain"
        and profile is not None
        and not profile.is_indoor
        and poi.primary_category in OUTDOOR_RAIN_CATEGORIES
    )


def build_baseline_matrix(
    session: Session,
    ordered_poi_ids: Sequence[int],
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> BaselineMatrixResult:
    """Build [start, poi..., end] matrix using cheap estimates."""
    poi_by_id = {
        poi.id: poi
        for poi in session.query(PoiMaster).filter(PoiMaster.id.in_(list(ordered_poi_ids))).all()
    }
    node_ids = [-1, *ordered_poi_ids, -2]
    coords = [
        (origin_lat, origin_lng),
        *[(poi_by_id[poi_id].lat, poi_by_id[poi_id].lng) for poi_id in ordered_poi_ids],
        (dest_lat, dest_lng),
    ]
    return BaselineMatrixResult(
        node_ids=node_ids,
        matrix=[
            [
                0
                if i == j
                else estimate_drive_minutes(start[0], start[1], end[0], end[1])
                for j, end in enumerate(coords)
            ]
            for i, start in enumerate(coords)
        ],
    )


def prune_candidates(
    *,
    candidate_poi_ids: Sequence[int],
    must_visit: set[int],
    excluded: set[int],
    plan_date: date,
    weather_mode: str,
    session: Session,
) -> list[int]:
    """Drop excluded/inactive/weather-blocked nodes while preserving must visits."""
    _ = plan_date
    kept: list[int] = []
    for poi_id in candidate_poi_ids:
        if poi_id in excluded:
            continue
        poi = session.get(PoiMaster, poi_id)
        if poi is None or not poi.is_active or _is_weather_blocked(poi, weather_mode):
            continue
        kept.append(poi_id)
    for poi_id in must_visit:
        if poi_id in excluded or poi_id in kept:
            continue
        poi = session.get(PoiMaster, poi_id)
        if poi is not None and not _is_weather_blocked(poi, weather_mode):
            kept.append(poi_id)
    order = {poi_id: index for index, poi_id in enumerate(candidate_poi_ids)}
    return sorted(set(kept), key=lambda poi_id: order.get(poi_id, 999))


def shortlist_nodes(
    candidate_ids: Sequence[int],
    must_visit: set[int],
    max_nodes: int = DEFAULT_SHORTLIST_MAX,
) -> list[int]:
    """Keep must_visit and only the top optional nodes for the reduced graph."""
    must = [poi_id for poi_id in candidate_ids if poi_id in must_visit]
    optional = [poi_id for poi_id in candidate_ids if poi_id not in must_visit]
    return must + optional[: max(0, max_nodes - len(must))]


def _ensure_required_categories(
    session: Session,
    shortlist_ids: list[int],
    candidate_ids: Sequence[int],
    *,
    must_visit: set[int],
    weather_mode: str,
    satisfied_categories: set[str] | None = None,
    max_nodes: int = DEFAULT_SHORTLIST_MAX,
) -> list[int]:
    category_map = {
        poi.id: poi.primary_category
        for poi in session.query(PoiMaster).filter(PoiMaster.id.in_(candidate_ids)).all()
    }
    required_categories = ["lunch", "dinner", "sweets"]
    if weather_mode != "rain":
        required_categories.append("sunset")
    ensured = list(shortlist_ids)
    for category_name in required_categories:
        if (
            category_name in (satisfied_categories or set())
            or any(category_map.get(poi_id) == category_name for poi_id in ensured)
        ):
            continue
        fallback = next(
            (poi_id for poi_id in candidate_ids if category_map.get(poi_id) == category_name),
            None,
        )
        if fallback is None:
            continue
        ensured.append(fallback)
        while len(ensured) > max_nodes:
            removable = next(
                (
                    poi_id
                    for poi_id in reversed(ensured)
                    if poi_id not in must_visit and poi_id != fallback
                ),
                None,
            )
            if removable is None:
                break
            ensured.remove(removable)
    return list(dict.fromkeys(ensured))


def cache_key_parts(
    o_lat: float,
    o_lng: float,
    d_lat: float,
    d_lng: float,
    plan_day: date,
    bucket: str,
    preference: str,
) -> tuple[str, str, str, str, str]:
    return (
        _hash_coords(o_lat, o_lng),
        _hash_coords(d_lat, d_lng),
        plan_day.isoformat(),
        bucket,
        preference,
    )


def _cache_lookup(
    session: Session,
    cache_parts: tuple[str, str, str, str, str],
) -> RoutingCacheEntry | None:
    origin_hash, destination_hash, plan_day_type, departure_bucket, routing_preference = cache_parts
    return (
        session.query(RoutingCacheEntry)
        .filter(
            RoutingCacheEntry.origin_hash == origin_hash,
            RoutingCacheEntry.destination_hash == destination_hash,
            RoutingCacheEntry.plan_day_type == plan_day_type,
            RoutingCacheEntry.departure_bucket == departure_bucket,
            RoutingCacheEntry.routing_preference == routing_preference,
        )
        .order_by(RoutingCacheEntry.id.desc())
        .first()
    )


def get_cached_duration(
    session: Session,
    o_lat: float,
    o_lng: float,
    d_lat: float,
    d_lng: float,
    plan_day: date,
    bucket: str,
    preference: str,
) -> int | None:
    row = _cache_lookup(
        session,
        cache_key_parts(o_lat, o_lng, d_lat, d_lng, plan_day, bucket, preference),
    )
    return None if row is None else int(row.duration_seconds // 60)


def put_cached_duration(
    session: Session,
    o_lat: float,
    o_lng: float,
    d_lat: float,
    d_lng: float,
    plan_day: date,
    bucket: str,
    preference: str,
    duration_seconds: int,
    distance_meters: int | None = None,
) -> None:
    parts = cache_key_parts(o_lat, o_lng, d_lat, d_lng, plan_day, bucket, preference)
    existing = _cache_lookup(session, parts)
    if existing is None:
        origin_hash, destination_hash, plan_day_type, departure_bucket, routing_preference = parts
        session.add(
            RoutingCacheEntry(
                origin_hash=origin_hash,
                destination_hash=destination_hash,
                plan_day_type=plan_day_type,
                departure_bucket=departure_bucket,
                routing_preference=routing_preference,
                duration_seconds=duration_seconds,
                distance_meters=distance_meters,
            )
        )
        return
    existing.duration_seconds = duration_seconds
    existing.distance_meters = distance_meters


def log_routing_request(
    session: Session,
    *,
    request_kind: str,
    element_count: int,
    latency_ms: int,
    estimated_cost_usd: float,
    cache_hit: bool,
    notes: str | None = None,
) -> None:
    session.add(
        RoutingRequestLog(
            request_kind=request_kind,
            element_count=element_count,
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost_usd,
            cache_hit=cache_hit,
            notes=notes,
            recorded_at=datetime.now(timezone.utc),
        )
    )


def _estimate_matrix(
    node_ids: Sequence[int],
    coords_by_node: dict[int, tuple[float, float]],
) -> list[list[int]]:
    size = len(node_ids)
    matrix = [[0] * size for _ in range(size)]
    for i, j, origin_node, destination_node in _iter_pairs(node_ids):
        origin = coords_by_node[origin_node]
        destination = coords_by_node[destination_node]
        matrix[i][j] = estimate_drive_minutes(
            origin[0], origin[1], destination[0], destination[1]
        )
    return matrix


def _routing_preference(bucket: str, shortlist_size: int) -> str:
    return (
        "TRAFFIC_AWARE_OPTIMAL"
        if bucket in TRAFFIC_INTENSIVE_BUCKETS and shortlist_size <= 8
        else "TRAFFIC_AWARE"
    )


async def _build_bucket_matrix(
    session: Session,
    trip: TripPlan,
    node_ids: list[int],
    coords_by_node: dict[int, tuple[float, float]],
    bucket: str,
    departure_min: int,
    *,
    use_traffic_matrix: bool,
    routing_preference: str,
) -> list[list[int]]:
    size = len(node_ids)
    matrix = [[0] * size for _ in range(size)]
    cache_complete = True
    for i, j, origin_node, destination_node in _iter_pairs(node_ids):
        origin = coords_by_node[origin_node]
        destination = coords_by_node[destination_node]
        cached = get_cached_duration(
            session,
            origin[0],
            origin[1],
            destination[0],
            destination[1],
            trip.plan_date,
            bucket,
            routing_preference,
        )
        if cached is None:
            cache_complete = False
        else:
            matrix[i][j] = cached
    element_count = size * size - size
    if cache_complete:
        log_routing_request(
            session,
            request_kind=f"computeRouteMatrix:{bucket}",
            element_count=element_count,
            latency_ms=0,
            estimated_cost_usd=0.0,
            cache_hit=True,
            notes="all matrix elements served from cache",
        )
        return matrix
    if not use_traffic_matrix or not settings.google_maps_api_key:
        return _estimate_matrix(node_ids, coords_by_node)

    started = time_module.perf_counter()
    api_matrix = await compute_route_matrix_minutes(
        [coords_by_node[node_id] for node_id in node_ids],
        [coords_by_node[node_id] for node_id in node_ids],
        departure_bucket=bucket,
        traffic_aware=routing_preference != "TRAFFIC_UNAWARE",
        departure_time_iso=_minute_to_iso(trip.plan_date, departure_min),
        routing_preference=routing_preference,
    )
    latency_ms = int((time_module.perf_counter() - started) * 1000)
    for i, j, origin_node, destination_node in _iter_pairs(node_ids):
        duration_min = int(api_matrix[i][j])
        origin = coords_by_node[origin_node]
        destination = coords_by_node[destination_node]
        put_cached_duration(
            session,
            origin[0],
            origin[1],
            destination[0],
            destination[1],
            trip.plan_date,
            bucket,
            routing_preference,
            duration_seconds=duration_min * 60,
        )
        matrix[i][j] = duration_min
    log_routing_request(
        session,
        request_kind=f"computeRouteMatrix:{bucket}",
        element_count=element_count,
        latency_ms=latency_ms,
        estimated_cost_usd=element_count * ROUTE_MATRIX_COST_PER_ELEMENT_USD,
        cache_hit=False,
        notes=f"traffic matrix built for {bucket}",
    )
    return matrix


def _active_candidate_defaults(
    active_candidates: list[TripCandidate],
) -> tuple[list[int], set[int], set[int], dict[int, int]]:
    return (
        [
            candidate.poi_id
            for candidate in active_candidates
            if not candidate.excluded and not candidate.locked_out
        ],
        {
            candidate.poi_id
            for candidate in active_candidates
            if candidate.must_visit or candidate.locked_in
        },
        {
            candidate.poi_id
            for candidate in active_candidates
            if candidate.excluded or candidate.locked_out
        },
        {
            candidate.poi_id: candidate.utility_override
            for candidate in active_candidates
            if candidate.utility_override is not None
        },
    )


def _departure_times(result: SolverResult, departure_min: int) -> list[int]:
    departure_times = [
        result.start_departure_min if result.start_departure_min is not None else departure_min
    ]
    departure_times.extend(
        (result.departure_minutes[index] or departure_min)
        for index in range(min(len(result.ordered_poi_ids), len(result.departure_minutes)))
    )
    return departure_times


async def build_solve_pipeline(
    session: Session,
    trip: TripPlan,
    *,
    use_traffic_matrix: bool,
    origin_override: tuple[float, float] | None = None,
    departure_start_min: int | None = None,
    departure_window_end_min: int | None = None,
    candidate_ids: list[int] | None = None,
    must_visit: set[int] | None = None,
    excluded_ids: set[int] | None = None,
    utility_overrides: dict[int, int] | None = None,
    max_continuous_drive_minutes: int | None = None,
    satisfied_categories: set[str] | None = None,
    cafe_requirement_already_met: bool = False,
) -> SolvePipelineResult:
    active_candidates = (
        session.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip.id, TripCandidate.status == "active")
        .all()
    )
    default_ids, default_must, default_excluded, default_utilities = _active_candidate_defaults(
        active_candidates
    )
    candidate_ids = default_ids if candidate_ids is None else candidate_ids
    must_visit = default_must if must_visit is None else must_visit
    excluded_ids = default_excluded if excluded_ids is None else excluded_ids
    utility_overrides = default_utilities if utility_overrides is None else utility_overrides

    preference_profile = trip.preference_profile
    departure_min = (
        departure_start_min
        if departure_start_min is not None
        else trip.departure_window_start_min
    )
    departure_window_end = (
        departure_window_end_min
        if departure_window_end_min is not None
        else trip.departure_window_end_min
    )
    start_lat, start_lng = origin_override or (trip.origin_lat, trip.origin_lng)
    pruned_ids = prune_candidates(
        candidate_poi_ids=candidate_ids,
        must_visit=must_visit,
        excluded=excluded_ids,
        plan_date=trip.plan_date,
        weather_mode=trip.weather_mode,
        session=session,
    )
    effective_must_visit = {poi_id for poi_id in must_visit if poi_id in pruned_ids}
    removed_must_visit = sorted(must_visit - effective_must_visit)
    shortlist_max = pace_shortlist_max(
        preference_profile.pace_style if preference_profile is not None else "balanced"
    )
    shortlist_ids = _ensure_required_categories(
        session,
        shortlist_nodes(pruned_ids, effective_must_visit, max_nodes=shortlist_max),
        pruned_ids,
        must_visit=effective_must_visit,
        weather_mode=trip.weather_mode,
        satisfied_categories=satisfied_categories,
        max_nodes=shortlist_max,
    )
    baseline = build_baseline_matrix(
        session,
        shortlist_ids,
        start_lat,
        start_lng,
        trip.dest_lat,
        trip.dest_lng,
    )
    coords_by_node = {
        -1: (start_lat, start_lng),
        -2: (trip.dest_lat, trip.dest_lng),
        **{
            poi.id: (poi.lat, poi.lng)
            for poi in session.query(PoiMaster).filter(PoiMaster.id.in_(shortlist_ids)).all()
        },
    }
    category_by_poi_id = {
        poi_id: poi.primary_category
        for poi_id, poi in {
            poi.id: poi
            for poi in session.query(PoiMaster).filter(PoiMaster.id.in_(shortlist_ids)).all()
        }.items()
    }
    used_traffic = use_traffic_matrix and bool(settings.google_maps_api_key)
    matrix_by_bucket = {"departure": baseline.matrix}
    if used_traffic:
        bucket_minutes = _bucket_departure_minutes(departure_min)
        for bucket in DEPARTURE_BUCKETS:
            matrix_by_bucket[bucket] = await _build_bucket_matrix(
                session,
                trip,
                baseline.node_ids,
                coords_by_node,
                bucket,
                bucket_minutes[bucket],
                use_traffic_matrix=used_traffic,
                routing_preference=_routing_preference(bucket, len(shortlist_ids)),
            )

    solver_input = SolverInput(
        origin_lat=start_lat,
        origin_lng=start_lng,
        dest_lat=trip.dest_lat,
        dest_lng=trip.dest_lng,
        departure_start_min=departure_min,
        departure_window_end_min=departure_window_end,
        return_deadline_min=trip.return_deadline_min,
        candidate_poi_ids=shortlist_ids,
        must_visit=effective_must_visit,
        driving_penalty_weight=(
            preference_profile.driving_penalty_weight if preference_profile else 0.05
        ),
        weather_mode=trip.weather_mode,
        plan_date=trip.plan_date,
        excluded_poi_ids=excluded_ids,
        utility_overrides=utility_overrides,
        max_continuous_drive_minutes=(
            max_continuous_drive_minutes
            or (
                preference_profile.max_continuous_drive_minutes
                if preference_profile
                else 120
            )
        ),
        preferred_lunch_tags=set(
            preference_profile.preferred_lunch_tags if preference_profile else []
        ),
        preferred_dinner_tags=set(
            preference_profile.preferred_dinner_tags if preference_profile else []
        ),
        must_have_cafe=preference_profile.must_have_cafe if preference_profile else False,
        satisfied_categories=satisfied_categories or set(),
        cafe_requirement_already_met=cafe_requirement_already_met,
        budget_band=preference_profile.budget_band if preference_profile else None,
        pace_style=preference_profile.pace_style if preference_profile else "balanced",
        matrix_node_ids=baseline.node_ids,
        travel_matrix=matrix_by_bucket["departure"],
    )
    solver_result = solve_trip(session, solver_input)
    selected_bucket = "departure"
    if used_traffic:
        selected_bucket = _select_bucket_from_result(
            solver_result,
            departure_min=solver_result.start_departure_min or departure_min,
            category_by_poi_id=category_by_poi_id,
        )
        if selected_bucket != "departure":
            solver_input.travel_matrix = matrix_by_bucket[selected_bucket]
            solver_result = solve_trip(session, solver_input)

    refined_legs: list[dict[str, Any]] = []
    if used_traffic and solver_result.feasible and solver_result.ordered_poi_ids:
        route_nodes = [-1, *solver_result.ordered_poi_ids, -2]
        refinement_requests = [
            LegRefinement(
                from_lat=coords_by_node[from_node][0],
                from_lng=coords_by_node[from_node][1],
                to_lat=coords_by_node[to_node][0],
                to_lng=coords_by_node[to_node][1],
                departure_time_iso=_minute_to_iso(
                    trip.plan_date,
                    _departure_times(solver_result, departure_min)[index]
                    if index < len(_departure_times(solver_result, departure_min))
                    else departure_min,
                ),
            )
            for index, (from_node, to_node) in enumerate(zip(route_nodes, route_nodes[1:]))
        ]
        refined_legs = await refine_legs(refinement_requests)
        log_routing_request(
            session,
            request_kind="computeRoutes:selected_legs",
            element_count=len(refinement_requests),
            latency_ms=0,
            estimated_cost_usd=0.0,
            cache_hit=False,
            notes="selected leg refinement",
        )
        refined_matrix = [row[:] for row in matrix_by_bucket[selected_bucket]]
        node_index = {node_id: index for index, node_id in enumerate(baseline.node_ids)}
        material_shift = False
        for index, refined_leg in enumerate(refined_legs):
            if index + 1 >= len(route_nodes):
                continue
            new_duration = int(refined_leg.get("duration_minutes", 0))
            if new_duration <= 0:
                continue
            from_node, to_node = route_nodes[index], route_nodes[index + 1]
            old_duration = refined_matrix[node_index[from_node]][node_index[to_node]]
            refined_matrix[node_index[from_node]][node_index[to_node]] = new_duration
            material_shift |= abs(new_duration - old_duration) >= 10
        if material_shift:
            solver_input.travel_matrix = refined_matrix
            refined_result = solve_trip(session, solver_input)
            if refined_result.feasible:
                solver_result = refined_result
                matrix_by_bucket[selected_bucket] = refined_matrix

    if trip.weather_mode == "rain" and removed_must_visit:
        solver_result.reason_codes = list(
            dict.fromkeys(
                solver_result.reason_codes
                + ["rain_mode_removed_outdoor_candidates"]
                + [
                    f"must_visit_{poi_id}_removed_by_rain_mode"
                    for poi_id in removed_must_visit
                ]
            )
        )

    return SolvePipelineResult(
        solver_result=solver_result,
        node_ids=baseline.node_ids,
        matrix=matrix_by_bucket[selected_bucket],
        shortlist_ids=shortlist_ids,
        refined_legs=refined_legs,
        used_bucket=selected_bucket,
        used_traffic_matrix=used_traffic,
    )
