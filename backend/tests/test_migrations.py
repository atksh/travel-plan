from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from app.db import database as database_module
from app.db.seed import run_seed
from app.models.poi import PoiMaster


def test_alembic_upgrade_and_seed_roundtrip(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    database_module.run_migrations(database_url=database_url)

    engine = database_module.build_engine(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert "poi_master" in table_names
    assert "trip_plan" in table_names
    assert "solver_run" in table_names
    poi_master_columns = {
        column["name"] for column in inspector.get_columns("poi_master")
    }
    assert "seed_key" in poi_master_columns
    poi_master_unique_constraints = inspector.get_unique_constraints("poi_master")
    assert any(
        set(constraint["column_names"]) == {"seed_key"}
        for constraint in poi_master_unique_constraints
    )
    trip_candidate_unique_constraints = inspector.get_unique_constraints(
        "trip_candidate"
    )
    assert any(
        set(constraint["column_names"]) == {"trip_id", "poi_id"}
        for constraint in trip_candidate_unique_constraints
    )
    planning_profile_columns = {
        column["name"] for column in inspector.get_columns("poi_planning_profile")
    }
    assert "price_band" in planning_profile_columns
    planned_stop_columns = {
        column["name"] for column in inspector.get_columns("planned_stop")
    }
    assert {"label", "lat", "lng"} <= planned_stop_columns

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        run_seed(session)
        assert session.query(PoiMaster).count() >= 21
    finally:
        session.close()
        engine.dispose()
