"""Google Places (New) and Routes API clients."""

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
    now = datetime.now(timezone.utc)
    if departure_time.astimezone(timezone.utc) <= now:
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
        details={"field_name": field_name, "duration": duration},
    )


async def search_places_text(query: str, region: str = "jp") -> list[dict[str, Any]]:
    """Places API (New) text search — returns simplified dicts."""
    _assert_api_key_configured()
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
        place_id = p.get("id")
        display_name = p.get("displayName")
        location = p.get("location")
        primary_type = p.get("primaryType")
        if not isinstance(place_id, str):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "Places search returned a place without a valid id.",
            )
        if not (
            isinstance(display_name, dict)
            and isinstance(display_name.get("text"), str)
        ):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "Places search returned a place without displayName.text.",
                details={"place_id": place_id},
            )
        if not (
            isinstance(location, dict)
            and isinstance(location.get("latitude"), (int, float))
            and isinstance(location.get("longitude"), (int, float))
        ):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "Places search returned a place without valid location.",
                details={"place_id": place_id},
            )
        if not isinstance(primary_type, str):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "Places search returned a place without primaryType.",
                details={"place_id": place_id},
            )
        out.append(
            {
                "place_id": place_id,
                "displayName": display_name,
                "location": location,
                "primaryType": primary_type,
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
    _assert_api_key_configured()

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
    Single departure time per request (API constraint).
    """
    n_o = len(origins)
    n_d = len(destinations)
    _assert_api_key_configured()

    # Routes API v2 computeRouteMatrix
    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters",
    }
    effective_routing_preference = routing_preference or (
        "TRAFFIC_AWARE" if traffic_aware else "TRAFFIC_UNAWARE"
    )
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
        "routingPreference": effective_routing_preference,
    }
    if effective_routing_preference != "TRAFFIC_UNAWARE":
        body["departureTime"] = _require_future_departure_time_iso(departure_time_iso)
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        rows = r.json()
    # Response is stream of RouteMatrixElement
    if not isinstance(rows, list):
        raise DependencyError(
            "GOOGLE_RESPONSE_INVALID",
            "computeRouteMatrix returned an invalid payload shape.",
        )
    matrix = [[0] * n_d for _ in range(n_o)]
    for el in rows:
        if not isinstance(el, dict):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "computeRouteMatrix returned a non-object element.",
            )
        origin_index = el.get("originIndex")
        destination_index = el.get("destinationIndex")
        if not isinstance(origin_index, int) or not isinstance(destination_index, int):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "computeRouteMatrix element is missing originIndex or destinationIndex.",
                details={"element": el},
            )
        if not (0 <= origin_index < n_o and 0 <= destination_index < n_d):
            raise DependencyError(
                "GOOGLE_RESPONSE_INVALID",
                "computeRouteMatrix returned out-of-range indices.",
                details={"element": el},
            )
        seconds = _parse_duration_seconds(el.get("duration"), field_name="duration")
        matrix[origin_index][destination_index] = max(1, seconds // 60)
    return matrix


async def compute_route_polyline(
    origin: tuple[float, float],
    destination: tuple[float, float],
    departure_time_iso: str | None = None,
    routing_preference: str = "TRAFFIC_AWARE",
) -> RouteLegDetails:
    """computeRoutes for one leg — polyline + duration."""
    _assert_api_key_configured()
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
    }
    if routing_preference != "TRAFFIC_UNAWARE":
        body["departureTime"] = _require_future_departure_time_iso(departure_time_iso)
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    routes = data.get("routes", [])
    if not routes:
        raise DependencyError(
            "GOOGLE_RESPONSE_INVALID",
            "computeRoutes returned no routes.",
            details={"origin": origin, "destination": destination},
        )
    route0 = routes[0]
    if not isinstance(route0, dict):
        raise DependencyError(
            "GOOGLE_RESPONSE_INVALID",
            "computeRoutes returned an invalid route payload.",
        )
    dur = route0.get("duration")
    polyline = route0.get("polyline")
    if not isinstance(polyline, dict) or not isinstance(
        polyline.get("encodedPolyline"), str
    ):
        raise DependencyError(
            "GOOGLE_RESPONSE_INVALID",
            "computeRoutes returned a route without encoded polyline.",
            details={"route": route0},
        )
    seconds = _parse_duration_seconds(dur, field_name="duration")
    distance_meters = route0.get("distanceMeters")
    if distance_meters is not None and not isinstance(distance_meters, int):
        raise DependencyError(
            "GOOGLE_RESPONSE_INVALID",
            "computeRoutes returned a non-integer distanceMeters.",
            details={"route": route0},
        )
    return RouteLegDetails(
        duration_minutes=max(1, seconds // 60),
        polyline=polyline["encodedPolyline"],
        distance_meters=distance_meters,
    )
