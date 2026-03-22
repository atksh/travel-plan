from __future__ import annotations

from app.models.place import Place


def _confirmed_execution_trip(client, db_session, trip_create_payload: dict) -> tuple[int, int]:
    created = client.post("/api/trips", json=trip_create_payload).json()
    trip_id = created["trip"]["id"]
    for place in db_session.query(Place).limit(2).all():
        client.post(f"/api/trips/{trip_id}/candidates", json={"place_id": place.id, "priority": "high"})
    preview = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 3}).json()
    client.post(f"/api/trips/{trip_id}/solve", json={"workspace_version": 3, "preview_id": preview["preview_id"]})
    client.post(f"/api/trips/{trip_id}/execution/start")
    first_place_id = db_session.query(Place).first().id
    return trip_id, first_place_id


def test_replan_preview_uses_current_location_when_provided(client, db_session, trip_create_payload: dict) -> None:
    trip_id, first_place_id = _confirmed_execution_trip(client, db_session, trip_create_payload)
    client.post(
        f"/api/trips/{trip_id}/execution/events",
        json={"event_type": "arrived", "payload": {"place_id": first_place_id}},
    )

    response = client.post(
        f"/api/trips/{trip_id}/execution/replan-preview",
        json={
            "workspace_version": 3,
            "current_context": {
                "current_lat": 35.2,
                "current_lng": 139.95,
                "current_minute": 930,
                "label": "現在地",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["solve"]["stops"][1]["label"] == "現在地"


def test_replan_acceptance_creates_new_active_run(client, db_session, trip_create_payload: dict) -> None:
    trip_id, first_place_id = _confirmed_execution_trip(client, db_session, trip_create_payload)
    client.post(
        f"/api/trips/{trip_id}/execution/events",
        json={"event_type": "arrived", "payload": {"place_id": first_place_id}},
    )
    preview = client.post(
        f"/api/trips/{trip_id}/execution/replan-preview",
        json={"workspace_version": 3, "current_context": {"current_lat": 35.2, "current_lng": 139.95, "current_minute": 930}},
    ).json()

    accepted = client.post(
        f"/api/trips/{trip_id}/execution/replan",
        json={"preview_id": preview["preview_id"], "workspace_version": 3},
    )

    assert accepted.status_code == 200
    assert accepted.json()["active_run_id"] == accepted.json()["solve_run_id"]


def test_replan_preview_can_include_draft_candidate_patch(client, db_session, trip_create_payload: dict) -> None:
    trip_id, _ = _confirmed_execution_trip(client, db_session, trip_create_payload)
    extra_place = db_session.query(Place).offset(2).first()
    added = client.post(
        f"/api/trips/{trip_id}/candidates",
        json={"place_id": extra_place.id, "priority": "backup"},
    ).json()

    preview = client.post(
        f"/api/trips/{trip_id}/execution/replan-preview",
        json={
            "workspace_version": 4,
                "current_context": {"current_lat": 35.2, "current_lng": 139.95, "current_minute": 720},
            "draft_candidate_patches": [{"candidate_id": added["id"], "priority": "must", "locked_in": True}],
        },
    )

    assert preview.status_code == 200
    assert extra_place.id in preview.json()["solve"]["selected_place_ids"]
