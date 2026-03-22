"""Golden scenarios around initial solve behavior."""

from __future__ import annotations

import asyncio
from datetime import date

from app.config import settings
from app.models.poi import PoiDependencyRule, PoiMaster, PoiOpeningRule
from app.models.trip import TripCandidate
from app.services.routing_costs import build_solve_pipeline
from app.solver.model import SolverInput, SolverResult, solve_trip
from tests.helpers import add_custom_poi, create_trip, setup_seeded_db, solve_for_trip


def build_custom_solver_input(
    candidate_ids: list[int],
    *,
    driving_penalty_weight: float = 0.05,
    preferred_lunch_tags: set[str] | None = None,
    preferred_dinner_tags: set[str] | None = None,
    must_have_cafe: bool = False,
    budget_band: str | None = None,
    pace_style: str = "balanced",
) -> SolverInput:
    return SolverInput(
        origin_lat=35.0,
        origin_lng=139.0,
        dest_lat=35.0,
        dest_lng=139.0,
        departure_start_min=8 * 60,
        departure_window_end_min=8 * 60,
        return_deadline_min=23 * 60,
        candidate_poi_ids=candidate_ids,
        must_visit=set(),
        driving_penalty_weight=driving_penalty_weight,
        weather_mode="normal",
        plan_date=date(2026, 3, 21),
        preferred_lunch_tags=preferred_lunch_tags or set(),
        preferred_dinner_tags=preferred_dinner_tags or set(),
        must_have_cafe=must_have_cafe,
        budget_band=budget_band,
        pace_style=pace_style,
    )


def test_normal_plan_generation() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    result = solve_for_trip(db, trip)
    db.close()

    assert result.feasible
    assert result.objective is not None
    assert 1 in result.ordered_poi_ids
    assert 7 in result.ordered_poi_ids


def test_rain_toggle() -> None:
    db = setup_seeded_db()
    trip = create_trip(db, weather_mode="rain")
    pipeline = asyncio.run(
        build_solve_pipeline(db, trip, use_traffic_matrix=False)
    )
    result = pipeline.solver_result
    visited_categories = {
        db.get(PoiMaster, poi_id).primary_category
        for poi_id in result.ordered_poi_ids
        if db.get(PoiMaster, poi_id) is not None
    }
    db.close()

    assert "sunset" not in visited_categories
    assert "rain_mode_removed_outdoor_candidates" in result.reason_codes


def test_must_visit_infeasible() -> None:
    db = setup_seeded_db()
    trip = create_trip(
        db,
        departure_window_start_min=14 * 60 + 15,
        departure_window_end_min=14 * 60 + 45,
    )
    result = solve_for_trip(db, trip, departure_start_min=14 * 60 + 15)
    db.close()

    assert not result.feasible
    assert any(code.startswith("must_visit_1_") for code in result.reason_codes)


def test_return_deadline_tightening() -> None:
    db = setup_seeded_db()
    relaxed_trip = create_trip(db, return_deadline_min=1500)
    tight_trip = create_trip(db, return_deadline_min=21 * 60)

    relaxed = solve_for_trip(db, relaxed_trip)
    tight = solve_for_trip(db, tight_trip)
    db.close()

    assert relaxed.feasible
    assert not tight.feasible or len(tight.ordered_poi_ids) <= len(relaxed.ordered_poi_ids)


def test_weekday_specific_opening_rules_are_closed_on_non_matching_days() -> None:
    db = setup_seeded_db()
    lunch = add_custom_poi(
        db,
        name="Lunch",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
        utility_default=10,
        meal_window_start_min=11 * 60,
        meal_window_end_min=14 * 60,
    )
    dinner = add_custom_poi(
        db,
        name="Dinner",
        primary_category="dinner",
        lat=35.02,
        lng=139.02,
        utility_default=10,
        meal_window_start_min=17 * 60 + 30,
        meal_window_end_min=20 * 60,
    )
    sweets = add_custom_poi(
        db,
        name="Sweets",
        primary_category="sweets",
        lat=35.03,
        lng=139.03,
        utility_default=10,
    )
    sunset = add_custom_poi(
        db,
        name="Sunset",
        primary_category="sunset",
        lat=35.04,
        lng=139.04,
        utility_default=10,
        is_indoor=False,
    )
    closed_hub = add_custom_poi(
        db,
        name="Closed On Monday",
        primary_category="hub",
        lat=35.05,
        lng=139.05,
        utility_default=100,
    )
    db.add(
        PoiOpeningRule(
            poi_id=closed_hub.id,
            weekday=1,
            open_minute=10 * 60,
            close_minute=18 * 60,
            valid_from=None,
            valid_to=None,
            holiday_note=None,
            last_admission_minute=None,
        )
    )
    db.commit()

    candidate_ids = [lunch.id, dinner.id, sweets.id, sunset.id, closed_hub.id]
    optional_input = build_custom_solver_input(candidate_ids)
    optional_input.plan_date = date(2026, 3, 23)
    optional_result = solve_trip(db, optional_input)

    must_visit_input = build_custom_solver_input(candidate_ids)
    must_visit_input.plan_date = date(2026, 3, 23)
    must_visit_input.must_visit = {closed_hub.id}
    must_visit_result = solve_trip(db, must_visit_input)
    db.close()

    assert optional_result.feasible is True
    assert closed_hub.id not in optional_result.ordered_poi_ids
    assert must_visit_result.feasible is False
    assert f"must_visit_{closed_hub.id}_not_candidate" in must_visit_result.reason_codes


def test_normal_weather_requires_a_sunset_candidate() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    sunset_ids = [
        poi.id
        for poi in db.query(PoiMaster).filter(PoiMaster.primary_category == "sunset").all()
    ]
    (
        db.query(TripCandidate)
        .filter(TripCandidate.trip_id == trip.id, TripCandidate.poi_id.in_(sunset_ids))
        .delete(synchronize_session=False)
    )
    db.commit()

    result = solve_for_trip(db, trip)
    db.close()

    assert result.feasible is False
    assert "no_sunset_candidate" in result.reason_codes


def test_traffic_pipeline_selects_dinner_bucket(monkeypatch) -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    monkeypatch.setattr(settings, "google_maps_api_key", "fake-api-key")

    async def fake_compute_route_matrix_minutes(
        origins,
        destinations,
        departure_bucket="departure",
        traffic_aware=True,
        departure_time_iso=None,
        routing_preference=None,
    ):
        del traffic_aware, departure_time_iso, routing_preference
        bucket_base = {
            "departure": 10,
            "late_morning": 11,
            "afternoon": 12,
            "sunset": 13,
            "dinner": 14,
        }[departure_bucket]
        return [
            [0 if i == j else bucket_base for j in range(len(destinations))]
            for i in range(len(origins))
        ]

    async def fake_refine_legs(legs):
        return [
            {
                "duration_minutes": 14,
                "polyline": {"encodedPolyline": "mock"},
                "distance_meters": 12000,
            }
            for _ in legs
        ]

    solve_matrix_samples: list[int] = []

    def fake_solve_trip(session, inp):
        del session
        assert inp.travel_matrix is not None
        solve_matrix_samples.append(inp.travel_matrix[0][1])
        return SolverResult(
            feasible=True,
            objective=42.0,
            ordered_poi_ids=[14],
            arrival_minutes=[17 * 60 + 30, 19 * 60],
            departure_minutes=[18 * 60 + 30, 19 * 60],
            leg_minutes=[inp.travel_matrix[0][1], inp.travel_matrix[1][2]],
            reason_codes=[],
            solve_ms=0,
        )

    monkeypatch.setattr(
        "app.services.routing_costs.compute_route_matrix_minutes",
        fake_compute_route_matrix_minutes,
    )
    monkeypatch.setattr("app.services.routing_costs.refine_legs", fake_refine_legs)
    monkeypatch.setattr("app.services.routing_costs.solve_trip", fake_solve_trip)

    pipeline = asyncio.run(
        build_solve_pipeline(db, trip, use_traffic_matrix=True)
    )
    db.close()

    assert pipeline.solver_result.feasible
    assert pipeline.used_traffic_matrix is True
    assert pipeline.used_bucket == "dinner"
    assert solve_matrix_samples == [10, 14]
    assert pipeline.matrix[0][1] == 14


def test_preferred_meal_tags_affect_route_choice() -> None:
    db = setup_seeded_db()
    lunch_pref = add_custom_poi(
        db,
        name="Lunch Seafood",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
        tags=["seafood"],
        utility_default=10,
    )
    lunch_plain = add_custom_poi(
        db,
        name="Lunch Plain",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
        utility_default=12,
    )
    dinner_pref = add_custom_poi(
        db,
        name="Dinner Romantic",
        primary_category="dinner",
        lat=35.02,
        lng=139.02,
        tags=["romantic"],
        utility_default=10,
    )
    dinner_plain = add_custom_poi(
        db,
        name="Dinner Plain",
        primary_category="dinner",
        lat=35.02,
        lng=139.02,
        utility_default=12,
    )
    sweets = add_custom_poi(
        db,
        name="Cafe Stop",
        primary_category="sweets",
        lat=35.03,
        lng=139.03,
        tags=["cafe"],
        utility_default=10,
    )
    sunset = add_custom_poi(
        db,
        name="Sunset",
        primary_category="sunset",
        lat=35.04,
        lng=139.04,
        utility_default=10,
        is_indoor=False,
    )
    candidate_ids = [
        lunch_pref.id,
        lunch_plain.id,
        dinner_pref.id,
        dinner_plain.id,
        sweets.id,
        sunset.id,
    ]

    base = solve_trip(db, build_custom_solver_input(candidate_ids))
    preferred = solve_trip(
        db,
        build_custom_solver_input(
            candidate_ids,
            preferred_lunch_tags={"seafood"},
            preferred_dinner_tags={"romantic"},
        ),
    )
    db.close()

    assert lunch_plain.id in base.ordered_poi_ids
    assert dinner_plain.id in base.ordered_poi_ids
    assert lunch_pref.id in preferred.ordered_poi_ids
    assert dinner_pref.id in preferred.ordered_poi_ids


def test_must_have_cafe_selects_cafe_stop() -> None:
    db = setup_seeded_db()
    lunch = add_custom_poi(
        db,
        name="Lunch",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
        utility_default=10,
    )
    dinner = add_custom_poi(
        db,
        name="Dinner",
        primary_category="dinner",
        lat=35.02,
        lng=139.02,
        utility_default=10,
    )
    sweets_cafe = add_custom_poi(
        db,
        name="Cafe Sweets",
        primary_category="sweets",
        lat=35.03,
        lng=139.03,
        tags=["cafe"],
        utility_default=10,
    )
    sweets_plain = add_custom_poi(
        db,
        name="Plain Sweets",
        primary_category="sweets",
        lat=35.03,
        lng=139.03,
        utility_default=12,
    )
    sunset = add_custom_poi(
        db,
        name="Sunset",
        primary_category="sunset",
        lat=35.04,
        lng=139.04,
        utility_default=10,
        is_indoor=False,
    )
    candidate_ids = [lunch.id, dinner.id, sweets_cafe.id, sweets_plain.id, sunset.id]

    base = solve_trip(db, build_custom_solver_input(candidate_ids))
    with_cafe = solve_trip(
        db,
        build_custom_solver_input(candidate_ids, must_have_cafe=True),
    )
    db.close()

    assert sweets_plain.id in base.ordered_poi_ids
    assert sweets_cafe.id in with_cafe.ordered_poi_ids


def test_missing_cafe_candidate_is_infeasible() -> None:
    db = setup_seeded_db()
    lunch = add_custom_poi(
        db,
        name="Lunch",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
    )
    dinner = add_custom_poi(
        db,
        name="Dinner",
        primary_category="dinner",
        lat=35.02,
        lng=139.02,
    )
    sweets = add_custom_poi(
        db,
        name="No Cafe Sweets",
        primary_category="sweets",
        lat=35.03,
        lng=139.03,
    )

    result = solve_trip(
        db,
        build_custom_solver_input(
            [lunch.id, dinner.id, sweets.id],
            must_have_cafe=True,
        ),
    )
    db.close()

    assert not result.feasible
    assert "no_cafe_candidate" in result.reason_codes


def test_budget_band_affects_dinner_selection() -> None:
    db = setup_seeded_db()
    lunch = add_custom_poi(
        db,
        name="Lunch",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
        utility_default=10,
    )
    sweets = add_custom_poi(
        db,
        name="Cafe",
        primary_category="sweets",
        lat=35.02,
        lng=139.02,
        tags=["cafe"],
        utility_default=10,
    )
    dinner_casual = add_custom_poi(
        db,
        name="Casual Dinner",
        primary_category="dinner",
        lat=35.03,
        lng=139.03,
        utility_default=10,
        price_band="casual",
    )
    dinner_premium = add_custom_poi(
        db,
        name="Premium Dinner",
        primary_category="dinner",
        lat=35.03,
        lng=139.03,
        utility_default=11,
        price_band="premium",
    )
    sunset = add_custom_poi(
        db,
        name="Sunset",
        primary_category="sunset",
        lat=35.04,
        lng=139.04,
        utility_default=10,
        is_indoor=False,
    )
    candidate_ids = [lunch.id, sweets.id, dinner_casual.id, dinner_premium.id, sunset.id]

    base = solve_trip(db, build_custom_solver_input(candidate_ids))
    casual = solve_trip(
        db,
        build_custom_solver_input(candidate_ids, budget_band="casual"),
    )
    db.close()

    assert dinner_premium.id in base.ordered_poi_ids
    assert dinner_casual.id in casual.ordered_poi_ids


def test_pace_style_changes_stop_count_and_stay_bounds() -> None:
    db = setup_seeded_db()
    lunch = add_custom_poi(
        db,
        name="Lunch",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
        utility_default=10,
        stay_min_minutes=30,
        stay_max_minutes=90,
    )
    dinner = add_custom_poi(
        db,
        name="Dinner",
        primary_category="dinner",
        lat=35.02,
        lng=139.02,
        utility_default=10,
        stay_min_minutes=30,
        stay_max_minutes=90,
    )
    sweets = add_custom_poi(
        db,
        name="Cafe",
        primary_category="sweets",
        lat=35.03,
        lng=139.03,
        tags=["cafe"],
        utility_default=10,
        stay_min_minutes=30,
        stay_max_minutes=90,
    )
    far_hub = add_custom_poi(
        db,
        name="Far Hub",
        primary_category="hub",
        lat=35.20,
        lng=139.00,
        utility_default=10,
        stay_min_minutes=30,
        stay_max_minutes=90,
    )
    sunset = add_custom_poi(
        db,
        name="Sunset",
        primary_category="sunset",
        lat=35.04,
        lng=139.04,
        utility_default=10,
        is_indoor=False,
        stay_min_minutes=30,
        stay_max_minutes=90,
    )
    candidate_ids = [lunch.id, dinner.id, sweets.id, far_hub.id, sunset.id]

    relaxed = solve_trip(
        db,
        build_custom_solver_input(
            candidate_ids,
            driving_penalty_weight=0.2,
            pace_style="relaxed",
        ),
    )
    packed = solve_trip(
        db,
        build_custom_solver_input(
            candidate_ids,
            driving_penalty_weight=0.2,
            pace_style="packed",
        ),
    )
    db.close()

    assert far_hub.id not in relaxed.ordered_poi_ids
    assert far_hub.id in packed.ordered_poi_ids

    relaxed_lunch_index = relaxed.ordered_poi_ids.index(lunch.id)
    packed_lunch_index = packed.ordered_poi_ids.index(lunch.id)
    relaxed_lunch_stay = (
        relaxed.departure_minutes[relaxed_lunch_index]
        - relaxed.arrival_minutes[relaxed_lunch_index]
    )
    packed_lunch_stay = (
        packed.departure_minutes[packed_lunch_index]
        - packed.arrival_minutes[packed_lunch_index]
    )
    assert relaxed_lunch_stay == 60
    assert packed_lunch_stay == 30


def test_heuristic_solver_honors_database_dependencies() -> None:
    db = setup_seeded_db()
    lunch = add_custom_poi(
        db,
        name="Lunch",
        primary_category="lunch",
        lat=35.01,
        lng=139.01,
        utility_default=10,
        meal_window_start_min=11 * 60,
        meal_window_end_min=14 * 60,
    )
    dinner = add_custom_poi(
        db,
        name="Dinner",
        primary_category="dinner",
        lat=35.02,
        lng=139.02,
        utility_default=10,
        meal_window_start_min=17 * 60 + 30,
        meal_window_end_min=20 * 60,
    )
    sweets = add_custom_poi(
        db,
        name="Sweets",
        primary_category="sweets",
        lat=35.03,
        lng=139.03,
        utility_default=10,
    )
    sunset = add_custom_poi(
        db,
        name="Sunset",
        primary_category="sunset",
        lat=35.04,
        lng=139.04,
        utility_default=10,
        is_indoor=False,
    )
    dependency_target = add_custom_poi(
        db,
        name="Dependency Target",
        primary_category="hub",
        lat=35.05,
        lng=139.05,
        utility_default=1,
    )
    dependency_driver = add_custom_poi(
        db,
        name="Dependency Driver",
        primary_category="hub",
        lat=35.0505,
        lng=139.0505,
        utility_default=50,
    )
    filler_hubs = [
        add_custom_poi(
            db,
            name=f"Hub {idx}",
            primary_category="hub",
            lat=35.06 + idx * 0.001,
            lng=139.06 + idx * 0.001,
            utility_default=5,
        )
        for idx in range(7)
    ]
    db.add(
        PoiDependencyRule(
            if_visit_poi_id=dependency_driver.id,
            require_poi_id=dependency_target.id,
            description="Custom heuristic dependency",
        )
    )
    db.commit()

    candidate_ids = [
        lunch.id,
        dinner.id,
        sweets.id,
        sunset.id,
        dependency_driver.id,
        dependency_target.id,
        *[hub.id for hub in filler_hubs],
    ]
    result = solve_trip(db, build_custom_solver_input(candidate_ids))
    db.close()

    assert len(candidate_ids) > 12
    assert result.feasible is True
    assert dependency_driver.id in result.ordered_poi_ids
    assert dependency_target.id in result.ordered_poi_ids
