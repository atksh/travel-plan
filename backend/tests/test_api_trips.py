from __future__ import annotations

from app.models.place import Place
from app.models.trip import Trip, TripCandidate


def test_create_trip_returns_empty_workspace(client, trip_create_payload: dict) -> None:
    response = client.post("/api/trips", json=trip_create_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["trip"]["title"] == "Sunday coast drive"
    assert body["workspace_version"] == 1
    assert body["candidates"] == []
    assert body["rules"] == []
    assert body["latest_accepted_run"] is None


def test_patch_trip_increments_workspace_version(client, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()

    response = client.patch(
        f"/api/trips/{created['trip']['id']}",
        json={"title": "Updated title"},
    )

    assert response.status_code == 200
    assert response.json()["trip"]["title"] == "Updated title"
    assert response.json()["workspace_version"] == 2


def test_add_patch_and_delete_candidate_updates_workspace(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()
    assert place is not None

    add_response = client.post(
        f"/api/trips/{created['trip']['id']}/candidates",
        json={"place_id": place.id, "priority": "high"},
    )
    assert add_response.status_code == 201
    candidate_id = add_response.json()["id"]
    assert add_response.json()["priority"] == "high"

    patch_response = client.patch(
        f"/api/trips/{created['trip']['id']}/candidates/{candidate_id}",
        json={
            "locked_in": True,
            "stay_override": {"min": 20, "preferred": 50, "max": 90},
            "time_preference": {"arrive_after_min": 600, "arrive_before_min": 720},
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["locked_in"] is True
    assert patch_response.json()["stay_override"]["preferred"] == 50

    delete_response = client.delete(
        f"/api/trips/{created['trip']['id']}/candidates/{candidate_id}"
    )
    assert delete_response.status_code == 200

    workspace = client.get(f"/api/trips/{created['trip']['id']}").json()
    assert workspace["candidates"] == []
    assert workspace["workspace_version"] == 4


def test_create_rule_and_list_rules(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()
    assert place is not None

    response = client.post(
        f"/api/trips/{created['trip']['id']}/rules",
        json={
            "rule_kind": "arrival_window",
            "scope": "candidate",
            "mode": "hard",
            "weight": None,
            "target": {"kind": "place", "value": place.id, "data": {}},
            "operator": "require_between",
            "parameters": {"arrive_after_min": 600, "arrive_before_min": 720},
            "carry_forward_strategy": "stay_active",
            "label": "午前中に到着",
            "description": None,
            "created_by_surface": "ui",
        },
    )

    assert response.status_code == 201
    listed = client.get(f"/api/trips/{created['trip']['id']}/rules")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["rule_kind"] == "arrival_window"


def test_list_trips_returns_recent_trip_summaries(client, trip_create_payload: dict) -> None:
    client.post("/api/trips", json=trip_create_payload)

    response = client.get("/api/trips")

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Sunday coast drive"


def test_trip_workspace_version_is_persisted_in_database(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    trip_id = created["trip"]["id"]

    client.patch(f"/api/trips/{trip_id}", json={"title": "Another title"})

    trip = db_session.get(Trip, trip_id)
    assert trip is not None
    assert trip.workspace_version == 2


def test_duplicate_candidate_is_rejected(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()
    assert place is not None

    first = client.post(
        f"/api/trips/{created['trip']['id']}/candidates",
        json={"place_id": place.id},
    )
    second = client.post(
        f"/api/trips/{created['trip']['id']}/candidates",
        json={"place_id": place.id},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["message"] == "Candidate already exists for this place."


def test_unknown_candidate_returns_404(client, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()

    response = client.patch(
        f"/api/trips/{created['trip']['id']}/candidates/99999",
        json={"locked_in": True},
    )

    assert response.status_code == 404


def test_delete_rule_removes_it_from_workspace(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()

    created_rule = client.post(
        f"/api/trips/{created['trip']['id']}/rules",
        json={
            "rule_kind": "selection_count",
            "scope": "trip",
            "mode": "soft",
            "weight": 3,
            "target": {"kind": "tag", "value": "scenic", "data": {}},
            "operator": "include",
            "parameters": {"min_count": 1},
            "carry_forward_strategy": "stay_active",
            "label": "景色を入れる",
            "description": None,
            "created_by_surface": "ui",
        },
    ).json()
    assert place is not None

    delete_response = client.delete(
        f"/api/trips/{created['trip']['id']}/rules/{created_rule['id']}"
    )
    assert delete_response.status_code == 200

    workspace = client.get(f"/api/trips/{created['trip']['id']}").json()
    assert workspace["rules"] == []


def test_trip_creation_validates_departure_window(client, trip_create_payload: dict) -> None:
    payload = dict(trip_create_payload)
    payload["departure_window_start_min"] = 600
    payload["departure_window_end_min"] = 500

    response = client.post("/api/trips", json=payload)

    assert response.status_code == 422


def test_workspace_contains_nested_place_summary(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()
    client.post(f"/api/trips/{created['trip']['id']}/candidates", json={"place_id": place.id})

    workspace = client.get(f"/api/trips/{created['trip']['id']}").json()

    assert workspace["candidates"][0]["place"]["name"] == place.name


def test_candidates_are_removed_from_database_on_delete(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()
    added = client.post(
        f"/api/trips/{created['trip']['id']}/candidates",
        json={"place_id": place.id},
    ).json()

    client.delete(f"/api/trips/{created['trip']['id']}/candidates/{added['id']}")

    assert db_session.get(TripCandidate, added["id"]) is None
