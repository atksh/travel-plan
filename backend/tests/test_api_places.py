from __future__ import annotations

import app.api.routes.places as places_routes
from app.models.place import Place


def test_list_places_returns_seeded_places(client) -> None:
    response = client.get("/api/places")

    assert response.status_code == 200
    assert len(response.json()["items"]) >= 6


def test_create_and_patch_manual_place(client) -> None:
    created = client.post(
        "/api/places",
        json={
            "name": "Manual place",
            "lat": 35.2,
            "lng": 139.8,
            "category": "parking",
            "tags": ["parking"],
            "traits": ["parking_available"],
            "visit_profile": {
                "stay_min_minutes": 5,
                "stay_preferred_minutes": 10,
                "stay_max_minutes": 15,
            },
            "availability_rules": [{"open_minute": 0, "close_minute": 1440, "closed_flag": False}],
        },
    )
    assert created.status_code == 201

    patched = client.patch(
        f"/api/places/{created.json()['id']}",
        json={"name": "Renamed place", "archived": True},
    )

    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed place"
    assert patched.json()["archived"] is True


def test_get_place_detail_returns_visit_profile(client, db_session) -> None:
    place = db_session.query(Place).first()

    response = client.get(f"/api/places/{place.id}")

    assert response.status_code == 200
    assert response.json()["visit_profile"]["stay_preferred_minutes"] >= 30


def test_delete_place_archives_when_used_by_trip(client, db_session, trip_create_payload: dict) -> None:
    trip = client.post("/api/trips", json=trip_create_payload).json()
    place = db_session.query(Place).first()
    client.post(f"/api/trips/{trip['trip']['id']}/candidates", json={"place_id": place.id})

    response = client.delete(f"/api/places/{place.id}")

    assert response.status_code == 200
    db_session.refresh(place)
    assert place.archived is True


def test_search_text_returns_mocked_results(client, monkeypatch) -> None:
    async def fake_search_places_text(query: str, region: str = "jp"):
        del region
        return [
            {
                "provider": "google_places",
                "provider_place_id": "abc123",
                "name": f"{query} cafe",
                "lat": 35.0,
                "lng": 139.8,
                "primary_type": "cafe",
                "rating": 4.5,
                "price_level": "PRICE_LEVEL_MODERATE",
            }
        ]

    monkeypatch.setattr(places_routes, "search_places_text", fake_search_places_text)

    response = client.post("/api/places/search-text", json={"query": "ocean", "region": "jp"})

    assert response.status_code == 200
    assert response.json()["results"][0]["provider_place_id"] == "abc123"


def test_search_area_returns_mocked_results(client, monkeypatch) -> None:
    async def fake_search_places_area(*, center_lat: float, center_lng: float, radius_m: int, included_types: list[str] | None = None):
        del center_lat, center_lng, radius_m, included_types
        return [
            {
                "provider": "google_places",
                "provider_place_id": "nearby-1",
                "name": "Nearby museum",
                "lat": 35.1,
                "lng": 139.9,
                "primary_type": "museum",
                "rating": 4.2,
                "price_level": None,
            }
        ]

    monkeypatch.setattr(places_routes, "search_places_area", fake_search_places_area)

    response = client.post(
        "/api/places/search-area",
        json={"center": {"lat": 35.0, "lng": 139.8}, "radius_m": 5000},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["provider_place_id"] == "nearby-1"


def test_import_place_creates_or_updates_place(client, db_session, monkeypatch) -> None:
    async def fake_get_place_details(provider_place_id: str, language_code: str = "ja", region_code: str = "JP"):
        del language_code, region_code
        return {
            "provider": "google_places",
            "provider_place_id": provider_place_id,
            "name": "Imported cafe",
            "lat": 35.12,
            "lng": 139.91,
            "primary_type": "cafe",
            "rating": 4.4,
            "price_level": "PRICE_LEVEL_MODERATE",
            "business_status": "OPERATIONAL",
            "website_uri": "https://example.com",
            "opening_hours": {
                "periods": [
                    {
                        "open": {"day": 1, "hour": 9, "minute": 0},
                        "close": {"day": 1, "hour": 18, "minute": 0},
                    }
                ]
            },
            "raw_payload": {"id": provider_place_id},
        }

    monkeypatch.setattr(places_routes, "get_place_details", fake_get_place_details)

    response = client.post(
        "/api/places/import",
        json={"provider": "google_places", "provider_place_id": "import-1", "overrides": {"tags": ["scenic"]}},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Imported cafe"
    assert "scenic" in response.json()["tags"]

    persisted = db_session.query(Place).filter(Place.name == "Imported cafe").one()
    assert persisted.source == "google_places"


def test_search_area_requires_center_or_bounds(client) -> None:
    response = client.post("/api/places/search-area", json={"radius_m": 1000})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RULE_VALIDATION_FAILED"
