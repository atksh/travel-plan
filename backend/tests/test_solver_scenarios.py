from __future__ import annotations

from app.models.place import Place


def _trip_with_candidates(client, db_session, trip_create_payload: dict, count: int = 2) -> int:
    created = client.post("/api/trips", json=trip_create_payload).json()
    trip_id = created["trip"]["id"]
    for place in db_session.query(Place).limit(count).all():
        client.post(f"/api/trips/{trip_id}/candidates", json={"place_id": place.id, "priority": "high"})
    return trip_id


def test_preview_with_candidates_produces_route(client, db_session, trip_create_payload: dict) -> None:
    trip_id = _trip_with_candidates(client, db_session, trip_create_payload, count=2)

    response = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 3})

    assert response.status_code == 200
    assert len(response.json()["solve"]["stops"]) >= 3
    assert response.json()["solve"]["summary"]["feasible"] is True


def test_hard_arrival_window_rule_is_reported(client, db_session, trip_create_payload: dict) -> None:
    trip_id = _trip_with_candidates(client, db_session, trip_create_payload, count=1)
    place = db_session.query(Place).first()
    client.post(
        f"/api/trips/{trip_id}/rules",
        json={
            "rule_kind": "arrival_window",
            "scope": "candidate",
            "mode": "hard",
            "weight": None,
            "target": {"kind": "place", "value": place.id, "data": {}},
            "operator": "require_between",
            "parameters": {"arrive_after_min": 600, "arrive_before_min": 900},
            "carry_forward_strategy": "stay_active",
            "label": "午前訪問",
            "description": None,
            "created_by_surface": "ui",
        },
    )

    response = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 3})

    assert response.status_code == 200
    assert any(result["rule_id"] for result in response.json()["solve"]["rule_results"])


def test_soft_preference_rule_affects_rule_results(client, db_session, trip_create_payload: dict) -> None:
    trip_id = _trip_with_candidates(client, db_session, trip_create_payload, count=2)

    client.post(
        f"/api/trips/{trip_id}/rules",
        json={
            "rule_kind": "preference_match",
            "scope": "trip",
            "mode": "soft",
            "weight": 5,
            "target": {"kind": "tag", "value": "scenic", "data": {}},
            "operator": "prefer",
            "parameters": {},
            "carry_forward_strategy": "stay_active",
            "label": "景色重視",
            "description": None,
            "created_by_surface": "ui",
        },
    )

    response = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 4})

    assert response.status_code == 200
    assert any(result["score_impact"] >= 0 for result in response.json()["solve"]["rule_results"])


def test_selection_exclude_rule_drops_matching_candidate(client, db_session, trip_create_payload: dict) -> None:
    trip_id = _trip_with_candidates(client, db_session, trip_create_payload, count=2)
    place = db_session.query(Place).filter(Place.category == "cafe").first()
    assert place is not None
    client.post(
        f"/api/trips/{trip_id}/rules",
        json={
            "rule_kind": "selection_exclude",
            "scope": "trip",
            "mode": "hard",
            "weight": None,
            "target": {"kind": "category", "value": "cafe", "data": {}},
            "operator": "exclude",
            "parameters": {},
            "carry_forward_strategy": "stay_active",
            "label": "カフェ除外",
            "description": None,
            "created_by_surface": "ui",
        },
    )

    response = client.post(f"/api/trips/{trip_id}/preview", json={"workspace_version": 4})

    assert response.status_code == 200
    assert place.id not in response.json()["solve"]["selected_place_ids"]
