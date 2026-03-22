from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from app.db import database as database_module
from app.db.seed import run_seed
from app.models.place import Place


def test_alembic_upgrade_and_seed_roundtrip(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    database_module.run_migrations(database_url=database_url)

    engine = database_module.build_engine(database_url)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert {"place", "trip", "trip_rule", "solve_run", "execution_session"} <= table_names

    trip_columns = {column["name"] for column in inspector.get_columns("trip")}
    assert {
        "title",
        "plan_date",
        "workspace_version",
        "accepted_run_id",
        "end_constraint_kind",
    } <= trip_columns

    place_columns = {column["name"] for column in inspector.get_columns("place")}
    assert {"source", "archived", "category", "tags_json", "traits_json"} <= place_columns

    trip_candidate_unique_constraints = inspector.get_unique_constraints("trip_candidate")
    assert any(
        set(constraint["column_names"]) == {"trip_id", "place_id"}
        for constraint in trip_candidate_unique_constraints
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        run_seed(session)
        assert session.query(Place).count() >= 6
    finally:
        session.close()
        engine.dispose()
