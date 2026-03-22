"""Google Places (New) and Routes API clients. Uses mock data when API key is absent."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import settings


async def search_places_text(query: str, region: str = "jp") -> list[dict[str, Any]]:
    """Places API (New) text search — returns simplified dicts."""
    if not settings.google_maps_api_key:
        return [
            {
                "place_id": "mock_place",
                "displayName": {"text": f"Mock result for {query}"},
                "location": {"latitude": 35.1, "longitude": 140.1},
                "primaryType": "restaurant",
            }
        ]
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.primaryType",
    }
    body = {"textQuery": query, "regionCode": region}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    out: list[dict[str, Any]] = []
    for p in data.get("places", []):
        out.append(
            {
                "place_id": p.get("id"),
                "displayName": p.get("displayName"),
                "location": p.get("location"),
                "primaryType": p.get("primaryType"),
            }
        )
    return out


async def get_place_details(
    place_id: str,
    *,
    language_code: str = "ja",
    region_code: str = "JP",
) -> dict[str, Any]:
    """Place Details (New) using the official GET /v1/places/{placeId} endpoint."""
    normalized_place_id = place_id.removeprefix("places/")
    if not settings.google_maps_api_key:
        return {
            "id": normalized_place_id,
            "name": f"places/{normalized_place_id}",
            "displayName": {"text": f"Imported {normalized_place_id}"},
            "location": {"latitude": 35.1, "longitude": 140.1},
            "regularOpeningHours": {
                "periods": [
                    {
                        "open": {"day": 1, "hour": 10, "minute": 0},
                        "close": {"day": 1, "hour": 18, "minute": 0},
                    }
                ]
            },
            "businessStatus": "OPERATIONAL",
            "rating": 4.2,
            "userRatingCount": 120,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "primaryType": "restaurant",
            "websiteUri": None,
        }

    url = f"https://places.googleapis.com/v1/places/{normalized_place_id}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": ",".join(
            [
                "id",
                "name",
                "displayName",
                "location",
                "regularOpeningHours",
                "businessStatus",
                "rating",
                "userRatingCount",
                "priceLevel",
                "primaryType",
                "websiteUri",
            ]
        ),
    }
    params = {
        "languageCode": language_code,
        "regionCode": region_code,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


async def compute_route_matrix_minutes(
    origins: list[tuple[float, float]],
    destinations: list[tuple[float, float]],
    departure_bucket: str = "departure",
    traffic_aware: bool = True,
    departure_time_iso: str | None = None,
    routing_preference: str | None = None,
) -> list[list[int]]:
    """
    Routes API computeRouteMatrix — returns duration minutes matrix.
    Single departure time per request (API constraint). Mock if no key.
    """
    n_o = len(origins)
    n_d = len(destinations)
    if not settings.google_maps_api_key:
        time.sleep(0.01)
        # Simple mock: 30 min per cell
        return [[30 + i + j for j in range(n_d)] for i in range(n_o)]

    # Routes API v2 computeRouteMatrix
    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters",
    }
    # One departure time for all origins (per Google API contract)
    dep = departure_time_iso or "2026-03-21T09:00:00+09:00"
    body: dict[str, Any] = {
        "origins": [
            {"waypoint": {"location": {"latLng": {"latitude": la, "longitude": ln}}}}
            for la, ln in origins
        ],
        "destinations": [
            {"waypoint": {"location": {"latLng": {"latitude": la, "longitude": ln}}}}
            for la, ln in destinations
        ],
        "travelMode": "DRIVE",
        "routingPreference": routing_preference
        or ("TRAFFIC_AWARE" if traffic_aware else "TRAFFIC_UNAWARE"),
        "departureTime": dep,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        t0 = time.perf_counter()
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        latency_ms = int((time.perf_counter() - t0) * 1000)
        rows = r.json()
    # Response is stream of RouteMatrixElement
    matrix = [[0] * n_d for _ in range(n_o)]
    if isinstance(rows, list):
        for el in rows:
            oi = el.get("originIndex", 0)
            di = el.get("destinationIndex", 0)
            dur = el.get("duration", "0s")
            if isinstance(dur, str) and dur.endswith("s"):
                sec = int(dur[:-1])
            elif isinstance(dur, dict) and "seconds" in dur:
                sec = int(dur["seconds"])
            else:
                sec = int(dur) if isinstance(dur, (int, float)) else 0
            matrix[oi][di] = max(1, sec // 60)
    return matrix


async def compute_route_polyline(
    origin: tuple[float, float],
    destination: tuple[float, float],
    departure_time_iso: str | None = None,
    routing_preference: str = "TRAFFIC_AWARE",
) -> dict[str, Any]:
    """computeRoutes for one leg — polyline + duration."""
    if not settings.google_maps_api_key:
        return {
            "duration_minutes": 35,
            "polyline": None,
            "mock": True,
        }
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline",
    }
    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {
            "location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}
        },
        "travelMode": "DRIVE",
        "routingPreference": routing_preference,
        "departureTime": departure_time_iso or "2026-03-21T12:00:00+09:00",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    routes = data.get("routes", [])
    if not routes:
        return {"duration_minutes": 0, "polyline": None}
    route0 = routes[0]
    dur = route0.get("duration", "0s")
    if isinstance(dur, str) and dur.endswith("s"):
        minutes = max(1, int(dur[:-1]) // 60)
    else:
        minutes = 30
    return {
        "duration_minutes": minutes,
        "polyline": route0.get("polyline"),
        "distance_meters": route0.get("distanceMeters"),
    }
