from __future__ import annotations

from app.db.seed import run_seed
from app.models.place import Place


def test_run_seed_is_idempotent(db_session) -> None:
    before = db_session.query(Place).count()

    run_seed(db_session)
    after = db_session.query(Place).count()

    assert before == after


def test_run_seed_keeps_sample_places_queryable(db_session) -> None:
    run_seed(db_session)

    names = {place.name for place in db_session.query(Place).all()}

    assert {"Seaside Cafe", "Sunset Pier"} <= names
