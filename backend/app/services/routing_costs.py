"""Strict routing helpers for the generalized planner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.errors import DependencyError, StateContractError
from app.services.google_places import RouteLegDetails, compute_route_matrix_minutes, compute_route_polyline

JST = timedelta(hours=9)


@dataclass(slots=True)
class RouteNode:
    node_id: str
    lat: float
    lng: float


def minute_to_iso(plan_date: date, minute_of_day: int) -> str:
    days, minute = divmod(minute_of_day, 24 * 60)
    hour, minute = divmod(minute, 60)
    dt = datetime.combine(plan_date, time(hour=0, minute=0)).replace(
        tzinfo=datetime.now().astimezone().tzinfo
    ) + timedelta(days=days, hours=hour, minutes=minute)
    return dt.isoformat()


async def build_route_matrix(
    *,
    nodes: list[RouteNode],
    plan_date: date,
    departure_min: int,
    traffic_profile: str | None,
) -> list[list[int]]:
    if len(nodes) < 2:
        raise StateContractError(
            "ROUTING_DATA_INCOMPLETE",
            "At least two route nodes are required to build a route matrix.",
        )
    matrix = await compute_route_matrix_minutes(
        [(node.lat, node.lng) for node in nodes],
        [(node.lat, node.lng) for node in nodes],
        departure_time_iso=minute_to_iso(plan_date, departure_min),
        traffic_aware=(traffic_profile or "default") != "static",
        routing_preference="TRAFFIC_AWARE",
    )
    if len(matrix) != len(nodes) or any(len(row) != len(nodes) for row in matrix):
        raise DependencyError(
            "ROUTING_DATA_INCOMPLETE",
            "Route matrix response did not cover all nodes.",
        )
    return matrix


async def build_route_legs(
    *,
    coordinates: list[tuple[float, float]],
    plan_date: date,
    departure_minutes: list[int],
    traffic_profile: str | None,
) -> list[RouteLegDetails]:
    if len(coordinates) < 2:
        return []
    if len(departure_minutes) < len(coordinates) - 1:
        raise StateContractError(
            "ROUTING_DATA_INCOMPLETE",
            "Departure minute count did not match route leg count.",
        )
    routing_preference = "TRAFFIC_AWARE" if (traffic_profile or "default") != "static" else "TRAFFIC_UNAWARE"
    legs: list[RouteLegDetails] = []
    for index, (origin, destination) in enumerate(zip(coordinates, coordinates[1:])):
        legs.append(
            await compute_route_polyline(
                origin,
                destination,
                departure_time_iso=minute_to_iso(plan_date, departure_minutes[index]),
                routing_preference=routing_preference,
            )
        )
    return legs
