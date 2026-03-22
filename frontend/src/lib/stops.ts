import type { PlannedStopOut, PoiSummary, TripDetailOut } from "@/lib/types";

export type RoutePoint = {
  lat: number;
  lng: number;
  label: string;
};

export function stopToPoint(
  stop: PlannedStopOut,
  trip: Pick<
    TripDetailOut,
    "origin_lat" | "origin_lng" | "origin_label" | "dest_lat" | "dest_lng" | "dest_label"
  >,
  poiById: Map<number, PoiSummary>,
): RoutePoint | null {
  if (stop.lat !== null && stop.lat !== undefined && stop.lng !== null && stop.lng !== undefined) {
    return {
      lat: stop.lat,
      lng: stop.lng,
      label: stop.label || stop.poi_name || stop.node_kind,
    };
  }
  if (stop.node_kind === "start") {
    return {
      lat: trip.origin_lat,
      lng: trip.origin_lng,
      label: stop.label || stop.poi_name || trip.origin_label,
    };
  }
  if (stop.node_kind === "end") {
    return {
      lat: trip.dest_lat,
      lng: trip.dest_lng,
      label: stop.label || stop.poi_name || trip.dest_label,
    };
  }
  if (stop.poi_id === null) {
    return null;
  }
  const poi = poiById.get(stop.poi_id);
  if (!poi) {
    return null;
  }
  return {
    lat: poi.lat,
    lng: poi.lng,
    label: stop.label || stop.poi_name || poi.name,
  };
}

export function buildRoutePoints(
  stops: PlannedStopOut[],
  trip: Pick<
    TripDetailOut,
    "origin_lat" | "origin_lng" | "origin_label" | "dest_lat" | "dest_lng" | "dest_label"
  >,
  poiById: Map<number, PoiSummary>,
): RoutePoint[] {
  return stops
    .map((stop) => stopToPoint(stop, trip, poiById))
    .filter((point): point is RoutePoint => point !== null);
}
