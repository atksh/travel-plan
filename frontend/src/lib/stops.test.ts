import { describe, expect, it } from "vitest";
import { stopToPoint } from "@/lib/stops";
import type { PlannedStopOut, PoiSummary, TripDetailOut } from "@/lib/types";

const trip: Pick<
  TripDetailOut,
  "origin_lat" | "origin_lng" | "origin_label" | "dest_lat" | "dest_lng" | "dest_label"
> = {
  origin_lat: 35.727,
  origin_lng: 139.791,
  origin_label: "Tokyo Iriya",
  dest_lat: 35.727,
  dest_lng: 139.791,
  dest_label: "Tokyo Iriya return",
};

const poiById = new Map<number, PoiSummary>([
  [
    7,
    {
      id: 7,
      name: "Satomi no Yu",
      lat: 34.9985,
      lng: 139.868,
      google_place_id: null,
      primary_category: "healing",
      is_active: true,
    },
  ],
]);

describe("stopToPoint", () => {
  it("prefers persisted stop coordinates and label", () => {
    const stop: PlannedStopOut = {
      sequence_order: 0,
      poi_id: null,
      poi_name: "Start",
      label: "Current location",
      node_kind: "start",
      lat: 35.15,
      lng: 139.84,
      arrival_min: 480,
      departure_min: 480,
      stay_min: 0,
      leg_from_prev_min: null,
      status: "planned",
    };

    expect(stopToPoint(stop, trip, poiById)).toEqual({
      lat: 35.15,
      lng: 139.84,
      label: "Current location",
    });
  });

  it("falls back to trip and POI coordinates for older stop payloads", () => {
    const startStop: PlannedStopOut = {
      sequence_order: 0,
      poi_id: null,
      poi_name: "Start",
      node_kind: "start",
      arrival_min: 480,
      departure_min: 480,
      stay_min: 0,
      leg_from_prev_min: null,
      status: "planned",
    };
    const poiStop: PlannedStopOut = {
      sequence_order: 1,
      poi_id: 7,
      poi_name: "Satomi no Yu",
      node_kind: "poi",
      arrival_min: 600,
      departure_min: 660,
      stay_min: 60,
      leg_from_prev_min: 45,
      status: "planned",
    };

    expect(stopToPoint(startStop, trip, poiById)).toEqual({
      lat: 35.727,
      lng: 139.791,
      label: "Start",
    });
    expect(stopToPoint(poiStop, trip, poiById)).toEqual({
      lat: 34.9985,
      lng: 139.868,
      label: "Satomi no Yu",
    });
  });
});
