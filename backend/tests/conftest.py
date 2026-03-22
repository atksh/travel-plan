from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import database as database_module
from app.db.seed import run_seed
from app.main import app
from app.services import google_places as google_places_service
from app.services import routing_costs as routing_costs_service


@pytest.fixture(name="test_db_url")
def fixture_test_db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'integration.db'}"


@pytest.fixture(name="migrated_session_factory")
def fixture_migrated_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    test_db_url: str,
) -> Generator[sessionmaker, None, None]:
    monkeypatch.setattr(settings, "database_url", test_db_url)
    monkeypatch.setattr(settings, "google_maps_api_key", "test-google-maps-api-key")
    monkeypatch.setattr(settings, "cors_origins", "http://localhost:3000")

    test_engine = database_module.build_engine(test_db_url)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(database_module, "engine", test_engine)
    monkeypatch.setattr(database_module, "SessionLocal", testing_session_local)

    database_module.run_migrations(database_url=test_db_url)
    seed_session = testing_session_local()
    try:
        run_seed(seed_session)
    finally:
        seed_session.close()

    yield testing_session_local

    app.dependency_overrides.clear()
    test_engine.dispose()


@pytest.fixture(name="db_session")
def fixture_db_session(migrated_session_factory: sessionmaker) -> Generator[Session, None, None]:
    session = migrated_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(name="client")
def fixture_client(
    migrated_session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        db = migrated_session_factory()
        try:
            yield db
        finally:
            db.close()

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
            [0 if i == j else 15 + abs(i - j) for j in range(len(destinations))]
            for i in range(len(origins))
        ]

    async def fake_compute_route_polyline(
        origin,
        destination,
        departure_time_iso=None,
        routing_preference="TRAFFIC_AWARE",
    ):
        del origin, destination, departure_time_iso, routing_preference
        return google_places_service.RouteLegDetails(
            duration_minutes=18,
            polyline="encoded-polyline",
            distance_meters=12000,
        )

    monkeypatch.setattr(google_places_service, "compute_route_matrix_minutes", fake_compute_route_matrix_minutes)
    monkeypatch.setattr(google_places_service, "compute_route_polyline", fake_compute_route_polyline)
    monkeypatch.setattr(routing_costs_service, "compute_route_matrix_minutes", fake_compute_route_matrix_minutes)
    monkeypatch.setattr(routing_costs_service, "compute_route_polyline", fake_compute_route_polyline)
    app.dependency_overrides[database_module.get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(name="trip_create_payload")
def fixture_trip_create_payload() -> dict:
    return {
        "title": "Sunday coast drive",
        "plan_date": "2026-03-21",
        "origin": {"label": "Home", "lat": 35.72, "lng": 139.79},
        "destination": {"label": "Hotel", "lat": 35.45, "lng": 139.92},
        "departure_window_start_min": 480,
        "departure_window_end_min": 540,
        "end_constraint": {"kind": "arrive_by", "minute_of_day": 1260},
        "timezone": "Asia/Tokyo",
        "context": {"weather": None, "traffic_profile": "default"},
    }
