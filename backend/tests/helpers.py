from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.db.database import SessionLocal, reset_db
from app.db.seed import (
    DEFAULT_MUST_VISIT_SEED_KEYS,
    TRIP_CANDIDATE_SEED_KEYS,
    resolve_seed_poi_ids,
    run_seed,
)
from app.models.poi import PoiMaster, PoiOpeningRule, PoiPlanningProfile, PoiTag, PoiTagLink
from app.models.trip import TripCandidate, TripPlan, TripPreferenceProfile
from app.services.geo import estimate_drive_minutes
from app.solver.model import SolverInput, SolverResult, solve_trip


def setup_seeded_db() -> Session:
    reset_db()
    db = SessionLocal()
    run_seed(db)
    return db


def create_trip(
    db: Session,
    *,
    departure_window_start_min: int = 480,
    departure_window_end_min: int = 540,
    return_deadline_min: int = 1500,
    weather_mode: str = "normal",
) -> TripPlan:
    trip = TripPlan(
        plan_date=date(2026, 3, 21),
        origin_lat=35.727,
        origin_lng=139.791,
        dest_lat=35.727,
        dest_lng=139.791,
        origin_label="Tokyo Iriya",
        dest_label="Tokyo Iriya return",
        departure_window_start_min=departure_window_start_min,
        departure_window_end_min=departure_window_end_min,
        return_deadline_min=return_deadline_min,
        weather_mode=weather_mode,
    )
    db.add(trip)
    db.flush()
    db.add(
        TripPreferenceProfile(
            trip_id=trip.id,
            driving_penalty_weight=0.05,
            max_continuous_drive_minutes=120,
            preferred_lunch_tags=["seafood"],
            preferred_dinner_tags=["seafood"],
            must_have_cafe=False,
            budget_band="moderate",
            pace_style="balanced",
        )
    )
    candidate_ids = resolve_seed_poi_ids(db, TRIP_CANDIDATE_SEED_KEYS, trip_selectable_only=True)
    must_visit_ids = set(resolve_seed_poi_ids(db, DEFAULT_MUST_VISIT_SEED_KEYS))
    for poi_id in candidate_ids:
        db.add(
            TripCandidate(
                trip_id=trip.id,
                poi_id=poi_id,
                status="active",
                source="seed",
                excluded=False,
                must_visit=(poi_id in must_visit_ids),
            )
        )
    db.commit()
    db.refresh(trip)
    return trip


def trip_solver_input(
    db: Session,
    trip: TripPlan,
    *,
    departure_start_min: int | None = None,
    origin_override: tuple[float, float] | None = None,
) -> SolverInput:
    candidates = (
        db.query(TripCandidate)
        .filter(
            TripCandidate.trip_id == trip.id,
            TripCandidate.status == "active",
            TripCandidate.excluded.is_(False),
        )
        .all()
    )
    candidate_ids = [
        candidate.poi_id for candidate in candidates if not candidate.locked_out
    ]
    must_visit = {
        candidate.poi_id
        for candidate in candidates
        if candidate.must_visit or candidate.locked_in
    }
    origin_lat, origin_lng = origin_override or (
        trip.origin_lat,
        trip.origin_lng,
    )
    poi_rows = db.query(PoiMaster).filter(PoiMaster.id.in_(candidate_ids)).all()
    poi_by_id = {poi.id: poi for poi in poi_rows}
    matrix_node_ids = [-1, *candidate_ids, -2]
    coords_by_node = {
        -1: (origin_lat, origin_lng),
        -2: (trip.dest_lat, trip.dest_lng),
        **{
            poi_id: (poi_by_id[poi_id].lat, poi_by_id[poi_id].lng)
            for poi_id in candidate_ids
            if poi_id in poi_by_id
        },
    }
    travel_matrix = [
        [
            0
            if origin_node == destination_node
            else estimate_drive_minutes(
                coords_by_node[origin_node][0],
                coords_by_node[origin_node][1],
                coords_by_node[destination_node][0],
                coords_by_node[destination_node][1],
            )
            for destination_node in matrix_node_ids
        ]
        for origin_node in matrix_node_ids
    ]
    return SolverInput(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=trip.dest_lat,
        dest_lng=trip.dest_lng,
        departure_start_min=(
            departure_start_min
            if departure_start_min is not None
            else trip.departure_window_start_min
        ),
        departure_window_end_min=trip.departure_window_end_min,
        return_deadline_min=trip.return_deadline_min,
        candidate_poi_ids=candidate_ids,
        must_visit=must_visit,
        driving_penalty_weight=(
            trip.preference_profile.driving_penalty_weight
            if trip.preference_profile
            else 0.05
        ),
        weather_mode=trip.weather_mode,
        plan_date=trip.plan_date,
        max_continuous_drive_minutes=(
            trip.preference_profile.max_continuous_drive_minutes
            if trip.preference_profile
            else 120
        ),
        preferred_lunch_tags=set(
            trip.preference_profile.preferred_lunch_tags
            if trip.preference_profile
            else []
        ),
        preferred_dinner_tags=set(
            trip.preference_profile.preferred_dinner_tags
            if trip.preference_profile
            else []
        ),
        must_have_cafe=(
            trip.preference_profile.must_have_cafe
            if trip.preference_profile
            else False
        ),
        budget_band=trip.preference_profile.budget_band if trip.preference_profile else None,
        pace_style=trip.preference_profile.pace_style if trip.preference_profile else "balanced",
        matrix_node_ids=matrix_node_ids,
        travel_matrix=travel_matrix,
    )


def solve_for_trip(
    db: Session,
    trip: TripPlan,
    *,
    departure_start_min: int | None = None,
    origin_override: tuple[float, float] | None = None,
) -> SolverResult:
    return solve_trip(
        db,
        trip_solver_input(
            db,
            trip,
            departure_start_min=departure_start_min,
            origin_override=origin_override,
        ),
    )


def add_custom_poi(
    db: Session,
    *,
    name: str,
    primary_category: str = "hub",
    lat: float = 35.04,
    lng: float = 139.86,
    tags: list[str] | None = None,
    utility_default: int = 11,
    stay_min_minutes: int = 45,
    stay_max_minutes: int = 90,
    meal_window_start_min: int | None = None,
    meal_window_end_min: int | None = None,
    is_indoor: bool = True,
    price_band: str | None = None,
    with_default_opening_rule: bool = True,
) -> PoiMaster:
    poi = PoiMaster(
        name=name,
        lat=lat,
        lng=lng,
        google_place_id=None,
        primary_category=primary_category,
        is_active=True,
    )
    db.add(poi)
    db.flush()
    db.add(
        PoiPlanningProfile(
            poi_id=poi.id,
            stay_min_minutes=stay_min_minutes,
            stay_max_minutes=stay_max_minutes,
            meal_window_start_min=meal_window_start_min,
            meal_window_end_min=meal_window_end_min,
            is_indoor=is_indoor,
            sunset_score=0,
            scenic_score=1,
            relax_score=1,
            price_band=price_band,
            parking_note=None,
            difficulty_note="Test POI",
            utility_default=utility_default,
        )
    )
    if with_default_opening_rule:
        default_open_minute = meal_window_start_min or 9 * 60
        default_close_minute = meal_window_end_min or 18 * 60
        db.add(
            PoiOpeningRule(
                poi_id=poi.id,
                weekday=None,
                open_minute=default_open_minute,
                close_minute=default_close_minute,
                valid_from=None,
                valid_to=None,
                holiday_note=None,
                last_admission_minute=None,
            )
        )
    for slug in tags or []:
        tag = db.query(PoiTag).filter(PoiTag.slug == slug).one_or_none()
        if tag is None:
            tag = PoiTag(slug=slug, label=slug.replace("_", " ").title())
            db.add(tag)
            db.flush()
        db.add(PoiTagLink(poi_id=poi.id, tag_id=tag.id))
    db.commit()
    db.refresh(poi)
    return poi
