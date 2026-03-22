import type { PlannedStopOut } from "@/lib/types";

export type RoutePoint = {
  lat: number;
  lng: number;
  label: string;
};

export function stopToPoint(
  stop: PlannedStopOut,
): RoutePoint {
  return {
    lat: stop.lat,
    lng: stop.lng,
    label: stop.label,
  };
}

export function buildRoutePoints(
  stops: PlannedStopOut[],
): RoutePoint[] {
  return stops.map((stop) => stopToPoint(stop));
}
