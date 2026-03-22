"""Google Places and Routes API helpers for the generalized planner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.errors import DependencyError, RequestContractError


@dataclass(slots=True)
class RouteLegDetails:
    duration_minutes: int
    polyline: str
    distance_meters: int | None


def _assert_api_key_configured() -> None:
    if not settings.google_maps_api_key.strip():
        raise DependencyError(
            "GOOGLE_MAPS_API_KEY_MISSING",
            "Google Maps API key is required for this operation.",
            status_code=500,
        )


def _field_mask(fields: list[str]) -> str:
    return ",".join(fields)


def _normalize_provider_place(place: dict[str, Any]) -> dict[str, Any]:
    place_id = place.get("id")
    display_name = (place.get("displayName") or {}).get("text")
    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")
    if not isinstance(place_id, str):
        raise DependencyError("GOOGLE_RESPONSE_INVALID", "Place id is missing.")
    if not isinstance(display_name, str) or not display_name.strip():
        raise DependencyError(
            "GOOGLE_RESPONSE_INVALID",
            "Place displayName.text is missing.",
            details={"place_id": place_id},
        )
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        raise DependencyError(
            "GOOGLE_RESPONSE_INVALID",
            "Place location is missing.",
            details={"place_id": place_id},
        )
    primary_type = place.get("primaryType")
    rating = place.get("rating")
    price_level = place.get("priceLevel")
    return {
        "provider": "google_places",
        "provider_place_id": place_id.removeprefix("places/"),
        "name": display_name.strip(),
        "lat": float(lat),
        "lng": float(lng),
        "primary_type": primary_type if isinstance(primary_type, str) else None,
        "rating": float(rating) if isinstance(rating, (int, float)) else None,
        "price_level": price_level if isinstance(price_level, str) else None,
    }


async def search_places_text(query: str, region: str = "jp") -> list[dict[str, Any]]:
    _assert_api_key_configured()
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": _field_mask(
            [
                "places.id",
                "places.displayName",
                "places.location",
                "places.primaryType",
                "places.rating",
                "places.priceLevel",
            ]
        ),
    }
    body = {"textQuery": query, "regionCode": region}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    places = payload.get("places")
    if not isinstance(places, list):
        raise DependencyError("GOOGLE_RESPONSE_INVALID", "Places text search payload is invalid.")
    return [_normalize_provider_place(place) for place in places]


async def search_places_area(
    *,
    center_lat: float,
    center_lng: float,
    radius_m: int,
    included_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    _assert_api_key_configured()
    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": _field_mask(
            [
                "places.id",
                "places.displayName",
                "places.location",
                "places.primaryType",
                "places.rating",
                "places.priceLevel",
            ]
        ),
    }
    body: dict[str, Any] = {
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": center_lat, "longitude": center_lng},
                "radius": float(radius_m),
            }
        },
    }
    if included_types:
        body["includedTypes"] = included_types
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    places = payload.get("places")
    if not isinstance(places, list):
        raise DependencyError("GOOGLE_RESPONSE_INVALID", "Places nearby search payload is invalid.")
    return [_normalize_provider_place(place) for place in places]


async def get_place_details(
    provider_place_id: str,
    *,
    language_code: str = "ja",
    region_code: str = "JP",
) -> dict[str, Any]:
    _assert_api_key_configured()
    normalized = provider_place_id.removeprefix("places/")
    url = f"https://places.googleapis.com/v1/places/{normalized}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": _field_mask(
            [
                "id",
                "displayName",
                "location",
                "regularOpeningHours",
                "businessStatus",
                "rating",
                "priceLevel",
                "primaryType",
                "websiteUri",
            ]
        ),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            url,
            headers=headers,
            params={"languageCode": language_code, "regionCode": region_code},
        )
        response.raise_for_status()
        payload = response.json()
    normalized_place = _normalize_provider_place(payload)
    normalized_place["business_status"] = payload.get("businessStatus")
    normalized_place["website_uri"] = payload.get("websiteUri")
    normalized_place["opening_hours"] = payload.get("regularOpeningHours") or {}
    normalized_place["raw_payload"] = payload
    return normalized_place


def _require_future_departure_time_iso(departure_time_iso: str | None) -> str:
    if departure_time_iso is None:
        raise RequestContractError(
            "DEPARTURE_TIME_REQUIRED",
            "A future departure_time_iso is required for traffic-aware routing.",
        )
    try:
        departure_time = datetime.fromisoformat(departure_time_iso.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RequestContractError(
            "DEPARTURE_TIME_INVALID",
            "departure_time_iso must be a valid RFC3339 timestamp.",
            details={"departure_time_iso": departure_time_iso},
        ) from exc
    if departure_time.tzinfo is None:
        raise RequestContractError(
            "DEPARTURE_TIME_INVALID",
            "departure_time_iso must include timezone information.",
            details={"departure_time_iso": departure_time_iso},
        )
    if departure_time.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise RequestContractError(
            "DEPARTURE_TIME_IN_PAST",
            "departure_time_iso must be in the future.",
            details={"departure_time_iso": departure_time_iso},
        )
    return departure_time_iso


def _parse_duration_seconds(duration: Any, *, field_name: str) -> int:
    if isinstance(duration, str) and duration.endswith("s") and duration[:-1].isdigit():
        return int(duration[:-1])
    if isinstance(duration, dict) and isinstance(duration.get("seconds"), (int, float)):
        return int(duration["seconds"])
    raise DependencyError(
        "GOOGLE_RESPONSE_INVALID",
        f"Google response field '{field_name}' had an invalid duration shape.",
        details={"field_name": field_name},
    )


async def compute_route_matrix_minutes(
    origins: list[tuple[float, float]],
    destinations: list[tuple[float, float]],
    departure_bucket: str = "departure",
    traffic_aware: bool = True,
    departure_time_iso: str | None = None,
    routing_preference: str | None = None,
) -> list[list[int]]:
    del departure_bucket
    _assert_api_key_configured()
    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters",
    }
    effective_preference = routing_preference or (
        "TRAFFIC_AWARE" if traffic_aware else "TRAFFIC_UNAWARE"
    )
    body: dict[str, Any] = {
        "origins": [
            {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lng}}}}
            for lat, lng in origins
        ],
        "destinations": [
            {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lng}}}}
            for lat, lng in destinations
        ],
        "travelMode": "DRIVE",
        "routingPreference": effective_preference,
    }
    if effective_preference != "TRAFFIC_UNAWARE":
        body["departureTime"] = _require_future_departure_time_iso(departure_time_iso)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list):
        raise DependencyError("GOOGLE_RESPONSE_INVALID", "Route matrix payload is invalid.")
    matrix = [[0 for _ in destinations] for _ in origins]
    for row in rows:
        if not isinstance(row, dict):
            raise DependencyError("GOOGLE_RESPONSE_INVALID", "Route matrix row is invalid.")
        origin_index = row.get("originIndex")
        destination_index = row.get("destinationIndex")
        if not isinstance(origin_index, int) or not isinstance(destination_index, int):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "Route matrix row is missing indices.",
            )
        matrix[origin_index][destination_index] = max(
            1,
            _parse_duration_seconds(row.get("duration"), field_name="duration") // 60,
        )
    return matrix


async def compute_route_polyline(
    origin: tuple[float, float],
    destination: tuple[float, float],
    departure_time_iso: str | None = None,
    routing_preference: str = "TRAFFIC_AWARE",
) -> RouteLegDetails:
    _assert_api_key_configured()
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline",
    }
    body: dict[str, Any] = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {
            "location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}
        },
        "travelMode": "DRIVE",
        "routingPreference": routing_preference,
    }
    if routing_preference != "TRAFFIC_UNAWARE":
        body["departureTime"] = _require_future_departure_time_iso(departure_time_iso)
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise DependencyError("GOOGLE_RESPONSE_INVALID", "No routes were returned.")
    first = routes[0]
    polyline = (first.get("polyline") or {}).get("encodedPolyline")
    if not isinstance(polyline, str) or not polyline:
        raise DependencyError("GOOGLE_RESPONSE_INVALID", "Route polyline is missing.")
    distance_meters = first.get("distanceMeters")
    if distance_meters is not None and not isinstance(distance_meters, int):
        raise DependencyError("GOOGLE_RESPONSE_INVALID", "distanceMeters is invalid.")
    return RouteLegDetails(
        duration_minutes=max(
            1,
            _parse_duration_seconds(first.get("duration"), field_name="duration") // 60,
        ),
        polyline=polyline,
        distance_meters=distance_meters,
    )
