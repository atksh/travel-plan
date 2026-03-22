from __future__ import annotations

from app.models.poi import PoiMaster, PoiOpeningRule
from app.models.source import PoiSourceSnapshot
import app.api.routes.pois as pois_routes


def test_api_list_pois_excludes_internal_trip_nodes(client) -> None:
    response = client.get("/api/pois")

    assert response.status_code == 200
    returned_ids = {poi["id"] for poi in response.json()}
    assert 0 not in returned_ids
    assert 99 not in returned_ids


def test_api_poi_search_returns_mocked_results(client, monkeypatch) -> None:
    async def fake_search_places_text(query: str, region: str = "jp"):
        del region
        return [
            {
                "place_id": "mock-search-1",
                "displayName": {"text": f"{query} Result"},
                "location": {"latitude": 35.0, "longitude": 140.0},
                "primaryType": "restaurant",
            }
        ]

    monkeypatch.setattr(
        pois_routes,
        "search_places_text",
        fake_search_places_text,
    )

    response = client.post(
        "/api/pois/search",
        json={"query": "Tateyama cafe", "region": "jp"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["place_id"] == "mock-search-1"
    assert body["results"][0]["primaryType"] == "restaurant"


def test_api_poi_import_upserts_details_and_snapshots(
    client,
    db_session,
    monkeypatch,
) -> None:
    async def fake_get_place_details(
        place_id: str,
        language_code: str = "ja",
        region_code: str = "JP",
    ):
        del language_code, region_code
        return {
            "id": place_id,
            "name": f"places/{place_id}",
            "displayName": {"text": "Imported Seaside Cafe"},
            "location": {"latitude": 35.0123, "longitude": 139.8765},
            "regularOpeningHours": {
                "periods": [
                    {
                        "open": {"day": 1, "hour": 10, "minute": 0},
                        "close": {"day": 1, "hour": 18, "minute": 0},
                    }
                ]
            },
            "businessStatus": "OPERATIONAL",
            "rating": 4.5,
            "userRatingCount": 420,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "primaryType": "cafe",
            "websiteUri": "https://example.com",
        }

    monkeypatch.setattr(
        pois_routes,
        "get_place_details",
        fake_get_place_details,
    )

    response = client.post(
        "/api/pois/import",
        json={"place_id": "import-cafe-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["google_place_id"] == "import-cafe-1"
    assert body["name"] == "Imported Seaside Cafe"
    assert body["primary_category"] == "sweets"
    assert len(body["opening_rules"]) >= 1
    assert body["planning_profile"]["price_band"] == "moderate"
    assert "cafe" in body["tags"]

    poi = (
        db_session.query(PoiMaster)
        .filter(PoiMaster.google_place_id == "import-cafe-1")
        .one()
    )
    assert poi.planning_profile is not None
    assert poi.planning_profile.is_indoor is True
    assert poi.planning_profile.price_band == "moderate"

    opening_rules = (
        db_session.query(PoiOpeningRule)
        .filter(PoiOpeningRule.poi_id == poi.id)
        .all()
    )
    assert len(opening_rules) >= 1

    source_snapshot = (
        db_session.query(PoiSourceSnapshot)
        .filter(PoiSourceSnapshot.poi_id == poi.id)
        .order_by(PoiSourceSnapshot.id.desc())
        .first()
    )
    assert source_snapshot is not None
    assert source_snapshot.source_type == "google_places"


def test_api_poi_import_requires_category_override_for_restaurants(
    client,
    monkeypatch,
) -> None:
    async def fake_get_place_details(
        place_id: str,
        language_code: str = "ja",
        region_code: str = "JP",
    ):
        del language_code, region_code
        return {
            "id": place_id,
            "name": f"places/{place_id}",
            "displayName": {"text": "Imported Dinner Spot"},
            "location": {"latitude": 35.0123, "longitude": 139.8765},
            "regularOpeningHours": {
                "periods": [
                    {
                        "open": {"day": 1, "hour": 10, "minute": 0},
                        "close": {"day": 1, "hour": 21, "minute": 0},
                    }
                ]
            },
            "businessStatus": "OPERATIONAL",
            "rating": 4.5,
            "userRatingCount": 420,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "primaryType": "restaurant",
            "websiteUri": "https://example.com",
        }

    monkeypatch.setattr(
        pois_routes,
        "get_place_details",
        fake_get_place_details,
    )

    response = client.post(
        "/api/pois/import",
        json={"place_id": "restaurant-import-1"},
    )

    assert response.status_code == 400
    assert "category_override" in response.json()["detail"]


def test_api_poi_import_allows_restaurants_with_dinner_override(
    client,
    db_session,
    monkeypatch,
) -> None:
    async def fake_get_place_details(
        place_id: str,
        language_code: str = "ja",
        region_code: str = "JP",
    ):
        del language_code, region_code
        return {
            "id": place_id,
            "name": f"places/{place_id}",
            "displayName": {"text": "Imported Dinner Spot"},
            "location": {"latitude": 35.0123, "longitude": 139.8765},
            "regularOpeningHours": {
                "periods": [
                    {
                        "open": {"day": 1, "hour": 10, "minute": 0},
                        "close": {"day": 1, "hour": 21, "minute": 0},
                    }
                ]
            },
            "businessStatus": "OPERATIONAL",
            "rating": 4.5,
            "userRatingCount": 420,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "primaryType": "restaurant",
            "websiteUri": "https://example.com",
        }

    monkeypatch.setattr(
        pois_routes,
        "get_place_details",
        fake_get_place_details,
    )

    response = client.post(
        "/api/pois/import",
        json={"place_id": "restaurant-import-2", "category_override": "dinner"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["primary_category"] == "dinner"
    assert body["planning_profile"]["meal_window_start_min"] == 17 * 60 + 30
    assert body["planning_profile"]["meal_window_end_min"] == 20 * 60

    poi = (
        db_session.query(PoiMaster)
        .filter(PoiMaster.google_place_id == "restaurant-import-2")
        .one()
    )
    assert poi.primary_category == "dinner"
