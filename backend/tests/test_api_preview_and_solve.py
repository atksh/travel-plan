from __future__ import annotations

from app.models.place import Place
from app.models.solve import SolvePreview, SolveRun


def _prepare_trip_with_candidate(client, db_session, trip_create_payload: dict) -> tuple[int, int]:
    created = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()
    client.post(f"/api/trips/{created['trip']['id']}/candidates", json={"place_id": place.id, "priority": "high"})
    return created["trip"]["id"], place.id


def test_preview_returns_preview_id_and_workspace_version(client, db_session, trip_create_payload: dict) -> None:
    trip_id, _ = _prepare_trip_with_candidate(client, db_session, trip_create_payload)

    response = client.post(
        f"/api/trips/{trip_id}/preview",
        json={"workspace_version": 2, "draft_candidate_patches": [], "draft_rule_patches": [], "draft_order_edits": []},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preview_id"].startswith("pvw_")
    assert body["workspace_version"] == 2
    assert body["solve"]["summary"]["feasible"] is True


def test_preview_persists_db_row(client, db_session, trip_create_payload: dict) -> None:
    trip_id, _ = _prepare_trip_with_candidate(client, db_session, trip_create_payload)

    response = client.post(
        f"/api/trips/{trip_id}/preview",
        json={"workspace_version": 2},
    )

    assert response.status_code == 200
    preview = db_session.get(SolvePreview, response.json()["preview_id"])
    assert preview is not None
    assert preview.trip_id == trip_id


def test_solve_accepts_preview_and_persists_run(client, db_session, trip_create_payload: dict) -> None:
    trip_id, _ = _prepare_trip_with_candidate(client, db_session, trip_create_payload)
    preview = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 2}).json()

    response = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"workspace_version": 2, "preview_id": preview["preview_id"]},
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["solve"]["summary"]["feasible"] is True
    run = db_session.get(SolveRun, response.json()["solve_run_id"])
    assert run is not None
    assert run.run_kind == "planned"


def test_preview_promotion_rejects_workspace_mismatch(client, db_session, trip_create_payload: dict) -> None:
    trip_id, second_place_id = _prepare_trip_with_candidate(client, db_session, trip_create_payload)
    preview = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 2}).json()
    another_place = db_session.query(Place).filter(Place.id != second_place_id).first()
    client.post(f"/api/trips/{trip_id}/candidates", json={"place_id": another_place.id})

    response = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"workspace_version": 3, "preview_id": preview["preview_id"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "WORKSPACE_VERSION_MISMATCH"


def test_solve_run_list_and_detail_are_readable(client, db_session, trip_create_payload: dict) -> None:
    trip_id, _ = _prepare_trip_with_candidate(client, db_session, trip_create_payload)
    preview = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 2}).json()
    accepted = client.post(
        f"/api/trips/{trip_id}/solve",
        json={"workspace_version": 2, "preview_id": preview["preview_id"]},
    ).json()

    listed = client.get(f"/api/trips/{trip_id}/solve-runs")
    detail = client.get(f"/api/trips/{trip_id}/solve-runs/{accepted['solve_run_id']}")

    assert listed.status_code == 200
    assert listed.json()["items"][0]["solve_run_id"] == accepted["solve_run_id"]
    assert detail.status_code == 200
    assert len(detail.json()["stops"]) >= 2


def test_preview_respects_draft_order_edits(client, db_session, trip_create_payload: dict) -> None:
    created = client.post("/api/trips", json=trip_create_payload).json()
    trip_id = created["trip"]["id"]
    places = db_session.query(Place).limit(2).all()
    for place in places:
        client.post(f"/api/trips/{trip_id}/candidates", json={"place_id": place.id, "priority": "high"})

    response = client.post(
        f"/api/trips/{trip_id}/preview",
        json={"workspace_version": 3, "draft_order_edits": [places[1].id, places[0].id]},
    )

    assert response.status_code == 200
    selected = response.json()["solve"]["selected_place_ids"]
    assert selected[:2] == [places[1].id, places[0].id]
