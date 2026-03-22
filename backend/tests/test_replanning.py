"""Golden scenarios around day-of replanning."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.poi import PoiMaster, PoiTag, PoiTagLink
from app.models.trip import TripCandidate, TripExecutionEvent
from app.solver.replanner import (
    _current_replan_minute,
    ReplanContext,
    load_replan_context,
    prepare_replan_state,
    replan_trip,
)
from tests.helpers import add_custom_poi, create_trip, setup_seeded_db, solve_for_trip


def test_lunch_delay_replan() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    initial = solve_for_trip(db, trip)
    lunch_poi_id = initial.ordered_poi_ids[0]
    lunch_poi = db.get(PoiMaster, lunch_poi_id)
    delayed = replan_trip(
        db,
        ReplanContext(
            trip_id=trip.id,
            now_minute=14 * 60 + 15,
            current_lat=lunch_poi.lat if lunch_poi else None,
            current_lng=lunch_poi.lng if lunch_poi else None,
            completed_poi_ids=[lunch_poi_id],
            in_progress_poi_id=None,
        ),
    )
    db.close()

    assert delayed.reason_codes or delayed.ordered_poi_ids != initial.ordered_poi_ids


def test_candidate_insertion_mid_trip() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    initial = solve_for_trip(db, trip)
    first_stop = initial.ordered_poi_ids[0]
    first_poi = db.get(PoiMaster, first_stop)
    custom_poi = add_custom_poi(
        db,
        name="Indoor Art Stop",
        primary_category="hub",
        lat=35.02,
        lng=139.84,
    )
    db.add(
        TripCandidate(
            trip_id=trip.id,
            poi_id=custom_poi.id,
            status="active",
            source="user",
            excluded=False,
            must_visit=False,
            utility_override=50,
        )
    )
    (
        db.query(TripCandidate)
        .filter(
            TripCandidate.trip_id == trip.id,
            TripCandidate.poi_id.in_([2, 3, 4, 18]),
        )
        .delete(synchronize_session=False)
    )
    db.commit()

    replanned = replan_trip(
        db,
        ReplanContext(
            trip_id=trip.id,
            now_minute=10 * 60 + 45,
            current_lat=first_poi.lat if first_poi else None,
            current_lng=first_poi.lng if first_poi else None,
            completed_poi_ids=[first_stop],
            in_progress_poi_id=None,
        ),
    )
    db.close()

    assert custom_poi.id in replanned.ordered_poi_ids


def test_candidate_deletion_mid_trip() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    initial = solve_for_trip(db, trip)
    first_stop = initial.ordered_poi_ids[0]
    first_poi = db.get(PoiMaster, first_stop)
    removable_poi_id = next(
        poi_id for poi_id in reversed(initial.ordered_poi_ids) if poi_id not in {1, 7}
    )
    candidate = (
        db.query(TripCandidate)
        .filter(
            TripCandidate.trip_id == trip.id,
            TripCandidate.poi_id == removable_poi_id,
        )
        .one()
    )
    db.delete(candidate)
    db.commit()

    replanned = replan_trip(
        db,
        ReplanContext(
            trip_id=trip.id,
            now_minute=12 * 60 + 45,
            current_lat=first_poi.lat if first_poi else None,
            current_lng=first_poi.lng if first_poi else None,
            completed_poi_ids=[first_stop],
            in_progress_poi_id=None,
        ),
    )
    db.close()

    assert removable_poi_id not in replanned.ordered_poi_ids


def test_departed_lunch_counts_as_satisfied_for_replan() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    lunch_ids = {9, 10, 11, 12, 13}
    for candidate in db.query(TripCandidate).filter(TripCandidate.trip_id == trip.id):
        candidate.must_visit = False
        candidate.locked_in = False
        if candidate.poi_id in lunch_ids and candidate.poi_id != 10:
            db.delete(candidate)
    db.commit()

    lunch_poi = db.get(PoiMaster, 10)
    assert lunch_poi is not None

    replanned = replan_trip(
        db,
        ReplanContext(
            trip_id=trip.id,
            now_minute=12 * 60,
            current_lat=lunch_poi.lat,
            current_lng=lunch_poi.lng,
            completed_poi_ids=[10],
        ),
    )
    db.close()

    assert replanned.feasible is True
    assert "no_lunch_candidate" not in replanned.reason_codes
    assert not any(poi_id in lunch_ids for poi_id in replanned.ordered_poi_ids)


def test_skipped_lunch_does_not_count_as_satisfied_for_replan() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    lunch_ids = {9, 10, 11, 12, 13}
    for candidate in db.query(TripCandidate).filter(TripCandidate.trip_id == trip.id):
        candidate.must_visit = False
        candidate.locked_in = False
        if candidate.poi_id in lunch_ids and candidate.poi_id not in {9, 10}:
            db.delete(candidate)
    db.commit()

    skipped_lunch = db.get(PoiMaster, 10)
    assert skipped_lunch is not None

    replanned = replan_trip(
        db,
        ReplanContext(
            trip_id=trip.id,
            now_minute=12 * 60,
            current_lat=skipped_lunch.lat,
            current_lng=skipped_lunch.lng,
            skipped_poi_ids=[10],
        ),
    )
    db.close()

    assert replanned.feasible is True
    assert 9 in replanned.ordered_poi_ids
    assert "no_lunch_candidate" not in replanned.reason_codes


def test_load_replan_context_separates_completed_skipped_and_in_progress() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)
    cafe_tag = db.query(PoiTag).filter(PoiTag.slug == "cafe").one_or_none()
    if cafe_tag is None:
        cafe_tag = PoiTag(slug="cafe", label="Cafe")
        db.add(cafe_tag)
        db.flush()
    db.add(PoiTagLink(poi_id=10, tag_id=cafe_tag.id))
    db.add_all(
        [
            TripExecutionEvent(
                trip_id=trip.id,
                event_type="arrived",
                payload_json={"poi_id": 10},
                recorded_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
            ),
            TripExecutionEvent(
                trip_id=trip.id,
                event_type="departed",
                payload_json={"poi_id": 10},
                recorded_at=datetime(2026, 3, 21, 10, 30, tzinfo=timezone.utc),
            ),
            TripExecutionEvent(
                trip_id=trip.id,
                event_type="arrived",
                payload_json={"poi_id": 11},
                recorded_at=datetime(2026, 3, 21, 11, 0, tzinfo=timezone.utc),
            ),
            TripExecutionEvent(
                trip_id=trip.id,
                event_type="skipped",
                payload_json={"poi_id": 11},
                recorded_at=datetime(2026, 3, 21, 11, 5, tzinfo=timezone.utc),
            ),
            TripExecutionEvent(
                trip_id=trip.id,
                event_type="arrived",
                payload_json={"poi_id": 14},
                recorded_at=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db.commit()

    ctx = load_replan_context(db, trip.id)
    state = prepare_replan_state(
        db,
        ReplanContext(
            trip_id=trip.id,
            now_minute=ctx.now_minute,
            current_lat=ctx.current_lat,
            current_lng=ctx.current_lng,
            completed_poi_ids=ctx.completed_poi_ids,
            skipped_poi_ids=ctx.skipped_poi_ids,
            in_progress_poi_id=ctx.in_progress_poi_id,
        ),
    )
    db.close()

    assert ctx.completed_poi_ids == [10]
    assert ctx.skipped_poi_ids == [11]
    assert ctx.in_progress_poi_id == 14
    assert state.satisfied_categories >= {"lunch", "dinner"}
    assert state.cafe_requirement_already_met is True


def test_prepare_replan_state_keeps_sweets_candidates_for_pipeline_backfill() -> None:
    db = setup_seeded_db()
    trip = create_trip(db)

    state = prepare_replan_state(
        db,
        ReplanContext(
            trip_id=trip.id,
            now_minute=16 * 60,
            current_lat=None,
            current_lng=None,
        ),
    )
    db.close()

    assert {16, 17} <= set(state.remaining_candidate_ids)


def test_current_replan_minute_carries_time_past_midnight() -> None:
    now = datetime(2026, 3, 21, 15, 30, tzinfo=timezone.utc)

    assert _current_replan_minute(date(2026, 3, 21), now=now) == 24 * 60 + 30


def test_current_replan_minute_keeps_same_day_minutes_unchanged() -> None:
    now = datetime(2026, 3, 21, 2, 5, tzinfo=timezone.utc)

    assert _current_replan_minute(date(2026, 3, 21), now=now) == 11 * 60 + 5
