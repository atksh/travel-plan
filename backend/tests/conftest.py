from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import database as database_module
from app.db.seed import run_seed
from app.main import app


@pytest.fixture(name="test_db_url")
def fixture_test_db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'integration.db'}"


@pytest.fixture(name="migrated_session_factory")
def fixture_migrated_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    test_db_url: str,
) -> Generator[sessionmaker, None, None]:
    monkeypatch.setattr(settings, "database_url", test_db_url)

    test_engine = database_module.build_engine(test_db_url)
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )

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
def fixture_db_session(
    migrated_session_factory: sessionmaker,
) -> Generator[Session, None, None]:
    session = migrated_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(name="client")
def fixture_client(
    migrated_session_factory: sessionmaker,
) -> Generator[TestClient, None, None]:
    def override_get_db():
        db = migrated_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[database_module.get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(name="trip_create_payload")
def fixture_trip_create_payload() -> dict:
    return {
        "plan_date": "2026-03-21",
        "origin_lat": 35.727,
        "origin_lng": 139.791,
        "origin_label": "Tokyo Iriya",
        "dest_lat": 35.727,
        "dest_lng": 139.791,
        "dest_label": "Tokyo Iriya return",
        "departure_window_start_min": 480,
        "departure_window_end_min": 540,
        "return_deadline_min": 1500,
        "weather_mode": "normal",
    }
