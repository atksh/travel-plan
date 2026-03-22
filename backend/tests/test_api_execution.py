from __future__ import annotations

from app.models.execution import ExecutionSession
from app.models.place import Place


def _prepare_confirmed_trip(client, db_session, trip_create_payload: dict) -> tuple[int, int]:
    created = client.post("/api/trips", json=trip_create_payload).json()
    trip_id = created["trip"]["id"]
    place = db_session.query(Place).first()
    client.post(f"/api/trips/{trip_id}/candidates", json={"place_id": place.id, "priority": "high"})
    preview = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 2}).json()
    client.post(
        f"/api/trips/{trip_id}/solve",
        json={"workspace_version": 2, "preview_id": preview["preview_id"]},
    )
    return trip_id, place.id


def test_execution_start_creates_session(client, db_session, trip_create_payload: dict) -> None:
    trip_id, _ = _prepare_confirmed_trip(client, db_session, trip_create_payload)

    response = client.post(f"/api/trips/{trip_id}/execution/start")

    assert response.status_code == 200
    session = db_session.get(ExecutionSession, response.json()["execution_session_id"])
    assert session is not None
    assert response.json()["trip_state"] == "active"


def test_execution_bootstrap_returns_active_solve(client, db_session, trip_create_payload: dict) -> None:
    trip_id, _ = _prepare_confirmed_trip(client, db_session, trip_create_payload)
    client.post(f"/api/trips/{trip_id}/execution/start")

    response = client.get(f"/api/trips/{trip_id}/execution/bootstrap")

    assert response.status_code == 200
    assert response.json()["active_solve"]["summary"]["feasible"] is True


def test_execution_event_is_appended(client, db_session, trip_create_payload: dict) -> None:
    trip_id, place_id = _prepare_confirmed_trip(client, db_session, trip_create_payload)
    client.post(f"/api/trips/{trip_id}/execution/start")

    response = client.post(
        f"/api/trips/{trip_id}/execution/events",
        json={"event_type": "arrived", "payload": {"place_id": place_id}},
    )

    assert response.status_code == 200
    assert response.json()["event_type"] == "arrived"


def test_execution_replan_preview_and_acceptance(client, db_session, trip_create_payload: dict) -> None:
    trip_id, place_id = _prepare_confirmed_trip(client, db_session, trip_create_payload)
    client.post(f"/api/trips/{trip_id}/execution/start")
    client.post(
        f"/api/trips/{trip_id}/execution/events",
        json={"event_type": "arrived", "payload": {"place_id": place_id}},
    )

    preview = client.post(
        f"/api/trips/{trip_id}/execution/replan-preview",
        json={
            "workspace_version": 2,
            "current_context": {"current_lat": 35.1, "current_lng": 139.9, "current_minute": 900},
        },
    )
    assert preview.status_code == 200

    accepted = client.post(
        f"/api/trips/{trip_id}/execution/replan",
        json={"preview_id": preview.json()["preview_id"], "workspace_version": 2},
    )

    assert accepted.status_code == 200
    assert accepted.json()["accepted"] is True
    assert accepted.json()["active_run_id"] > 0


def test_execution_start_requires_confirmed_trip(client, trip_create_payload: dict) -> None:
    trip_id = client.post("/api/trips", json=trip_create_payload).json()["trip"]["id"]

    response = client.post(f"/api/trips/{trip_id}/execution/start")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPLAN_NOT_ALLOWED"
