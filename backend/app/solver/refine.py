"""Leg refinement hooks (computeRoutes) after an ordered route exists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.google_places import compute_route_polyline


@dataclass
class LegRefinement:
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    departure_time_iso: str | None = None
    routing_preference: str = "TRAFFIC_AWARE"


async def refine_legs(legs: list[LegRefinement]) -> list[dict[str, Any]]:
    """Call computeRoutes per leg (parallel in production)."""
    out: list[dict[str, Any]] = []
    for leg in legs:
        r = await compute_route_polyline(
            (leg.from_lat, leg.from_lng),
            (leg.to_lat, leg.to_lng),
            departure_time_iso=leg.departure_time_iso,
            routing_preference=leg.routing_preference,
        )
        out.append(r)
    return out
