from __future__ import annotations

from fastapi.testclient import TestClient

import app.api.routes.trips as trips_routes
import app.services.routing_costs as routing_costs
from app.config import settings
from app.db import database as database_module
from app.db.seed import (
    DEFAULT_MUST_VISIT_SEED_KEYS,
    TRIP_CANDIDATE_SEED_KEYS,
    resolve_seed_poi_ids,
    run_seed,
)
from app.main import app
from app.models.poi import PoiMaster
from app.models.trip import PlannedStop, SolverRun, TripCandidate, TripPlan
from app.services.google_places import RouteLegDetails
from app.solver.replanner import ReplanContext
from sqlalchemy.orm import sessionmaker


def test_api_solve_persists_solver_run(
    client,
    db_session,
    trip_create_payload: dict,
) -> None:
    create_response = client.post("/api/trips", json=trip_create_payload)
    assert create_response.status_code == 200
    trip_id = create_response.json()["id"]

    solve_response = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"use_traffic_matrix": False},
    )
    assert solve_response.status_code == 200
    body = solve_response.json()
    assert body["feasible"] is True
    assert body["solver_run_id"] is not None
    assert len(body["planned_stops"]) >= 3

    solver_run = (
        db_session.query(SolverRun)
        .filter(SolverRun.trip_id == trip_id)
        .order_by(SolverRun.id.desc())
        .first()
    )
    assert solver_run is not None
    assert solver_run.route_summary_json["used_traffic_matrix"] is False

    planned_stops = (
        db_session.query(PlannedStop)
        .filter(PlannedStop.solver_run_id == solver_run.id)
        .all()
    )
    assert len(planned_stops) == len(body["planned_stops"])

    preview_response = client.get(f"/api/trips/{trip_id}/route-preview")
    assert preview_response.status_code == 200
    assert len(preview_response.json()["solve"]["planned_stops"]) == len(
        body["planned_stops"]
    )


def test_api_create_trip_allows_empty_initial_must_visit_selection(
    client,
    trip_create_payload: dict,
) -> None:
    payload = dict(trip_create_payload)
    payload["initial_must_visit_poi_ids"] = []

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 200
    candidates = {candidate["poi_id"]: candidate for candidate in response.json()["candidates"]}
    assert candidates[1]["must_visit"] is False
    assert candidates[7]["must_visit"] is False


def test_api_create_trip_applies_initial_candidate_state_in_one_request(
    client,
    db_session,
    trip_create_payload: dict,
) -> None:
    extra_poi = PoiMaster(
        name="User-selected extra POI",
        lat=35.05,
        lng=139.88,
        google_place_id=None,
        primary_category="hub",
        is_active=True,
    )
    db_session.add(extra_poi)
    db_session.commit()
    db_session.refresh(extra_poi)

    payload = dict(trip_create_payload)
    payload["initial_must_visit_poi_ids"] = [extra_poi.id]
    payload["initial_excluded_poi_ids"] = [1]

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 200
    candidates = {candidate["poi_id"]: candidate for candidate in response.json()["candidates"]}
    assert candidates[1]["excluded"] is True
    assert candidates[1]["must_visit"] is False
    assert candidates[7]["must_visit"] is False
    assert candidates[extra_poi.id]["must_visit"] is True
    assert candidates[extra_poi.id]["source"] == "user"


def test_api_create_trip_excluding_default_must_visit_keeps_it_non_required(
    client,
    trip_create_payload: dict,
) -> None:
    payload = dict(trip_create_payload)
    payload["initial_excluded_poi_ids"] = [1]

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 200
    candidates = {candidate["poi_id"]: candidate for candidate in response.json()["candidates"]}
    assert candidates[1]["excluded"] is True
    assert candidates[1]["must_visit"] is False
    assert candidates[7]["must_visit"] is True


def test_api_create_trip_persists_preferences_from_initial_request(
    client,
    db_session,
    trip_create_payload: dict,
) -> None:
    payload = dict(trip_create_payload)
    payload["preferences"] = {
        "driving_penalty_weight": 0.08,
        "max_continuous_drive_minutes": 90,
        "preferred_lunch_tags": ["seafood", "quick"],
        "preferred_dinner_tags": ["romantic"],
        "must_have_cafe": True,
        "budget_band": "premium",
        "pace_style": "packed",
    }

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["preference_profile"] == payload["preferences"]
    trip = db_session.get(TripPlan, body["id"])
    assert trip is not None
    assert trip.preference_profile is not None
    assert trip.preference_profile.driving_penalty_weight == 0.08
    assert trip.preference_profile.max_continuous_drive_minutes == 90
    assert trip.preference_profile.preferred_lunch_tags == ["seafood", "quick"]
    assert trip.preference_profile.preferred_dinner_tags == ["romantic"]
    assert trip.preference_profile.must_have_cafe is True
    assert trip.preference_profile.budget_band == "premium"
    assert trip.preference_profile.pace_style == "packed"


def test_api_create_trip_rejects_overlapping_initial_candidate_state(
    client,
    trip_create_payload: dict,
) -> None:
    payload = dict(trip_create_payload)
    payload["initial_must_visit_poi_ids"] = [1]
    payload["initial_excluded_poi_ids"] = [1]

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "POIs cannot be both must-visit and excluded"


def test_api_create_trip_rejects_reversed_departure_window(
    client,
    trip_create_payload: dict,
) -> None:
    payload = dict(trip_create_payload)
    payload["departure_window_start_min"] = 9 * 60
    payload["departure_window_end_min"] = 8 * 60

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert len(detail) == 1
    assert "departure_window_end_min must be greater than or equal to departure_window_start_min" in detail[0]["msg"]


def test_api_create_trip_rejects_internal_must_visit_poi(
    client,
    trip_create_payload: dict,
) -> None:
    payload = dict(trip_create_payload)
    payload["initial_must_visit_poi_ids"] = [0]

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "POI cannot be selected for trips: 0"


def test_api_create_trip_rejects_internal_excluded_poi(
    client,
    trip_create_payload: dict,
) -> None:
    payload = dict(trip_create_payload)
    payload["initial_excluded_poi_ids"] = [99]

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "POI cannot be selected for trips: 99"


def test_api_create_trip_succeeds_on_unseeded_database(
    tmp_path,
    trip_create_payload: dict,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'unseeded.db'}"
    database_module.run_migrations(database_url=database_url)
    engine = database_module.build_engine(database_url)
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database_module.get_db] = override_get_db
    try:
        with TestClient(app) as unseeded_client:
            response = unseeded_client.post("/api/trips", json=trip_create_payload)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 200
    assert response.json()["candidates"] == []


def test_api_create_trip_resolves_default_seed_candidates_by_seed_key(
    tmp_path,
    trip_create_payload: dict,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'seed-key-defaults.db'}"
    database_module.run_migrations(database_url=database_url)
    engine = database_module.build_engine(database_url)
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    seed_session = testing_session_local()
    try:
        seed_session.add(
            PoiMaster(
                id=1,
                name="Imported place",
                lat=35.5,
                lng=139.5,
                google_place_id="places/imported-place",
                primary_category="hub",
                is_active=True,
            )
        )
        seed_session.commit()
        run_seed(seed_session)
        expected_candidate_ids = set(
            resolve_seed_poi_ids(
                seed_session,
                TRIP_CANDIDATE_SEED_KEYS,
                trip_selectable_only=True,
            )
        )
        expected_must_visit_ids = set(
            resolve_seed_poi_ids(seed_session, DEFAULT_MUST_VISIT_SEED_KEYS)
        )
    finally:
        seed_session.close()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database_module.get_db] = override_get_db
    try:
        with TestClient(app) as seeded_client:
            response = seeded_client.post("/api/trips", json=trip_create_payload)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    assert response.status_code == 200
    candidates = {candidate["poi_id"]: candidate for candidate in response.json()["candidates"]}
    assert 1 not in candidates
    assert set(candidates) == expected_candidate_ids
    assert {
        poi_id for poi_id, candidate in candidates.items() if candidate["must_visit"]
    } == expected_must_visit_ids
    assert all(candidate["source"] == "seed" for candidate in candidates.values())


def test_api_solve_with_traffic_matrix_uses_pipeline_mocks(
    client,
    db_session,
    trip_create_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "google_maps_api_key", "fake-api-key")

    async def fake_compute_route_matrix_minutes(
        origins,
        destinations,
        departure_bucket="departure",
        traffic_aware=True,
        departure_time_iso=None,
        routing_preference=None,
    ):
        del departure_bucket, traffic_aware, departure_time_iso, routing_preference
        return [
            [0 if i == j else 12 for j in range(len(destinations))]
            for i in range(len(origins))
        ]

    async def fake_refine_legs(legs):
        return [
            RouteLegDetails(
                duration_minutes=12,
                polyline="mock",
                distance_meters=12000,
            )
            for _ in legs
        ]

    monkeypatch.setattr(
        routing_costs,
        "compute_route_matrix_minutes",
        fake_compute_route_matrix_minutes,
    )
    monkeypatch.setattr(routing_costs, "refine_legs", fake_refine_legs)

    create_response = client.post("/api/trips", json=trip_create_payload)
    trip_id = create_response.json()["id"]

    solve_response = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"use_traffic_matrix": True},
    )
    assert solve_response.status_code == 200
    assert solve_response.json()["feasible"] is True

    solver_run = (
        db_session.query(SolverRun)
        .filter(SolverRun.trip_id == trip_id)
        .order_by(SolverRun.id.desc())
        .first()
    )
    assert solver_run is not None
    assert solver_run.route_summary_json["used_traffic_matrix"] is True
    assert len(solver_run.route_summary_json["route_legs"]) > 0


def test_api_solve_without_traffic_uses_traffic_unaware_matrix_and_refines_legs(
    client,
    db_session,
    trip_create_payload: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "google_maps_api_key", "fake-api-key")
    call_counts = {"matrix": 0, "refine": 0}

    async def fake_compute_route_matrix_minutes(
        origins,
        destinations,
        departure_bucket="departure",
        traffic_aware=True,
        departure_time_iso=None,
        routing_preference=None,
    ):
        del departure_bucket, traffic_aware, departure_time_iso, routing_preference
        call_counts["matrix"] += 1
        return [
            [0 if i == j else 12 for j in range(len(destinations))]
            for i in range(len(origins))
        ]

    async def fake_refine_legs(legs):
        del legs
        call_counts["refine"] += 1
        return []

    monkeypatch.setattr(
        routing_costs,
        "compute_route_matrix_minutes",
        fake_compute_route_matrix_minutes,
    )
    monkeypatch.setattr(routing_costs, "refine_legs", fake_refine_legs)

    create_response = client.post("/api/trips", json=trip_create_payload)
    trip_id = create_response.json()["id"]

    solve_response = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"use_traffic_matrix": False},
    )
    assert solve_response.status_code == 200
    assert solve_response.json()["feasible"] is True
    assert call_counts == {"matrix": 1, "refine": 1}

    solver_run = (
        db_session.query(SolverRun)
        .filter(SolverRun.trip_id == trip_id)
        .order_by(SolverRun.id.desc())
        .first()
    )
    assert solver_run is not None
    assert solver_run.route_summary_json["used_traffic_matrix"] is False
    assert solver_run.route_summary_json["route_legs"] == []


def test_api_solve_shifts_schedule_within_departure_window(
    client,
    trip_create_payload: dict,
) -> None:
    early_payload = dict(trip_create_payload)
    early_payload["departure_window_end_min"] = early_payload["departure_window_start_min"]
    late_payload = dict(trip_create_payload)
    late_payload["departure_window_end_min"] = 12 * 60

    early_trip_id = client.post("/api/trips", json=early_payload).json()["id"]
    late_trip_id = client.post("/api/trips", json=late_payload).json()["id"]

    early = client.post(
        f"/api/trips/{early_trip_id}/solve",
        json={"use_traffic_matrix": False},
    ).json()
    late = client.post(
        f"/api/trips/{late_trip_id}/solve",
        json={"use_traffic_matrix": False},
    ).json()

    assert early["ordered_poi_ids"] == late["ordered_poi_ids"]
    assert len(early["planned_stops"]) == len(late["planned_stops"])

    shift = (
        late["planned_stops"][0]["departure_min"]
        - early["planned_stops"][0]["departure_min"]
    )
    assert shift >= 0
    assert late["planned_stops"][0]["departure_min"] <= 12 * 60

    for early_stop, late_stop in zip(
        early["planned_stops"][1:],
        late["planned_stops"][1:],
        strict=True,
    ):
        assert early_stop["poi_id"] == late_stop["poi_id"]
        assert early_stop["node_kind"] == late_stop["node_kind"]
        assert late_stop["arrival_min"] - early_stop["arrival_min"] == shift
        assert late_stop["departure_min"] - early_stop["departure_min"] == shift


def test_api_add_candidate_rejects_unknown_poi(
    client,
    trip_create_payload: dict,
) -> None:
    trip_id = client.post("/api/trips", json=trip_create_payload).json()["id"]

    response = client.post(
        f"/api/trips/{trip_id}/candidates",
        json={"poi_id": 999999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "POI not found"


def test_api_add_candidate_rejects_internal_trip_poi(
    client,
    trip_create_payload: dict,
) -> None:
    trip_id = client.post("/api/trips", json=trip_create_payload).json()["id"]

    response = client.post(
        f"/api/trips/{trip_id}/candidates",
        json={"poi_id": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "POI cannot be selected for trips: 0"


def test_api_add_candidate_rejects_duplicate_trip_poi(
    client,
    db_session,
    trip_create_payload: dict,
) -> None:
    extra_poi = PoiMaster(
        name="Duplicate candidate target",
        lat=35.05,
        lng=139.88,
        google_place_id=None,
        primary_category="hub",
        is_active=True,
    )
    db_session.add(extra_poi)
    db_session.commit()
    db_session.refresh(extra_poi)

    trip_id = client.post("/api/trips", json=trip_create_payload).json()["id"]

    first = client.post(
        f"/api/trips/{trip_id}/candidates",
        json={"poi_id": extra_poi.id},
    )
    second = client.post(
        f"/api/trips/{trip_id}/candidates",
        json={"poi_id": extra_poi.id},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == trips_routes.DUPLICATE_CANDIDATE_DETAIL
    assert (
        db_session.query(TripCandidate)
        .filter(
            TripCandidate.trip_id == trip_id,
            TripCandidate.poi_id == extra_poi.id,
        )
        .count()
        == 1
    )


def test_api_replan_appends_event_and_new_solver_run(
    client,
    db_session,
    trip_create_payload: dict,
    monkeypatch,
) -> None:
    create_response = client.post("/api/trips", json=trip_create_payload)
    trip_id = create_response.json()["id"]

    solve_response = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"use_traffic_matrix": False},
    )
    planned_stops = solve_response.json()["planned_stops"]
    current_stop = next(stop for stop in planned_stops if stop["node_kind"] == "poi")
    current_poi = db_session.get(PoiMaster, current_stop["poi_id"])
    assert current_poi is not None

    arrived_response = client.post(
        f"/api/trips/{trip_id}/events",
        json={
            "event_type": "arrived",
            "payload": {"poi_id": current_stop["poi_id"]},
        },
    )
    assert arrived_response.status_code == 200

    monkeypatch.setattr(
        trips_routes,
        "load_replan_context",
        lambda _db, _trip_id: ReplanContext(
            trip_id=trip_id,
            now_minute=11 * 60,
            current_lat=None,
            current_lng=None,
            completed_poi_ids=[],
            skipped_poi_ids=[],
            in_progress_poi_id=current_stop["poi_id"],
        ),
    )

    replan_response = client.post(
        f"/api/trips/{trip_id}/replan",
        json={
            "current_lat": current_poi.lat,
            "current_lng": current_poi.lng,
        },
    )
    assert replan_response.status_code == 200
    replan_body = replan_response.json()
    assert "planned_stops" in replan_body
    assert replan_body["planned_stops"][0]["departure_min"] == 11 * 60

    events_response = client.get(f"/api/trips/{trip_id}/events")
    assert events_response.status_code == 200
    assert any(
        event["event_type"] == "replanned" for event in events_response.json()
    )

    solver_run_count = db_session.query(SolverRun).filter(
        SolverRun.trip_id == trip_id
    ).count()
    assert solver_run_count >= 2


def test_api_replan_keeps_sweets_candidates_available_for_backfill(
    client,
    trip_create_payload: dict,
    monkeypatch,
) -> None:
    create_response = client.post("/api/trips", json=trip_create_payload)
    trip_id = create_response.json()["id"]

    monkeypatch.setattr(
        trips_routes,
        "load_replan_context",
        lambda _db, _trip_id: ReplanContext(
            trip_id=trip_id,
            now_minute=16 * 60,
            current_lat=None,
            current_lng=None,
            completed_poi_ids=[],
            skipped_poi_ids=[],
            in_progress_poi_id=None,
        ),
    )

    replan_response = client.post(f"/api/trips/{trip_id}/replan", json={})

    assert replan_response.status_code == 200
    assert "no_sweets_candidate" not in replan_response.json()["reason_codes"]


def test_api_replan_persists_live_start_metadata(
    client,
    db_session,
    trip_create_payload: dict,
    monkeypatch,
) -> None:
    create_response = client.post("/api/trips", json=trip_create_payload)
    trip_id = create_response.json()["id"]

    solve_response = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"use_traffic_matrix": False},
    )
    current_stop = next(
        stop for stop in solve_response.json()["planned_stops"] if stop["node_kind"] == "poi"
    )
    current_poi = db_session.get(PoiMaster, current_stop["poi_id"])
    assert current_poi is not None

    monkeypatch.setattr(
        trips_routes,
        "load_replan_context",
        lambda _db, _trip_id: ReplanContext(
            trip_id=trip_id,
            now_minute=11 * 60,
            current_lat=None,
            current_lng=None,
            completed_poi_ids=[],
            skipped_poi_ids=[],
            in_progress_poi_id=current_stop["poi_id"],
        ),
    )

    live_lat = current_poi.lat
    live_lng = current_poi.lng
    replan_response = client.post(
        f"/api/trips/{trip_id}/replan",
        json={"current_lat": live_lat, "current_lng": live_lng},
    )

    assert replan_response.status_code == 200
    start_stop = replan_response.json()["planned_stops"][0]
    assert start_stop["label"] == "Current location"
    assert start_stop["lat"] == live_lat
    assert start_stop["lng"] == live_lng

    preview_response = client.get(f"/api/trips/{trip_id}/route-preview")
    assert preview_response.status_code == 200
    persisted_start = preview_response.json()["solve"]["planned_stops"][0]
    assert persisted_start["label"] == "Current location"
    assert persisted_start["lat"] == live_lat
    assert persisted_start["lng"] == live_lng

    latest_run = (
        db_session.query(SolverRun)
        .filter(SolverRun.trip_id == trip_id)
        .order_by(SolverRun.id.desc())
        .first()
    )
    assert latest_run is not None
    persisted_planned_stop = (
        db_session.query(PlannedStop)
        .filter(PlannedStop.solver_run_id == latest_run.id)
        .order_by(PlannedStop.sequence_order.asc())
        .first()
    )
    assert persisted_planned_stop is not None
    assert persisted_planned_stop.label == "Current location"
    assert persisted_planned_stop.lat == live_lat
    assert persisted_planned_stop.lng == live_lng
