import { describe, expect, it } from "vitest";
import {
  ACTIVE_TRIP_POIS_UNAVAILABLE_MESSAGE,
  loadActiveTripBootstrap,
} from "@/lib/active-trip";
import type {
  EventOut,
  PoiSummary,
  RoutePreviewOut,
  TripDetailOut,
} from "@/lib/types";

const TRIP: TripDetailOut = {
  id: 1,
  state: "draft",
  plan_date: "2026-03-21",
  origin_lat: 35.727,
  origin_lng: 139.791,
  origin_label: "Tokyo Iriya",
  dest_lat: 35.727,
  dest_lng: 139.791,
  dest_label: "Tokyo Iriya return",
  departure_window_start_min: 480,
  departure_window_end_min: 540,
  return_deadline_min: 1500,
  weather_mode: "normal",
  preference_profile: null,
  candidates: [],
  latest_route: [],
  latest_solver_run: null,
};

const PREVIEW: RoutePreviewOut = {
  stops: [],
};

const EVENTS: EventOut[] = [
  {
    id: 1,
    event_type: "arrived",
    payload_json: { poi_id: 7 },
    recorded_at: "2026-03-21T00:00:00Z",
  },
];

const POIS: PoiSummary[] = [
  {
    id: 7,
    name: "Satomi no Yu",
    lat: 34.9985,
    lng: 139.868,
    google_place_id: null,
    primary_category: "healing",
    is_active: true,
  },
];

describe("loadActiveTripBootstrap", () => {
  it("returns all payloads when every request succeeds", async () => {
    const result = await loadActiveTripBootstrap({
      loadTrip: async () => TRIP,
      loadPreview: async () => PREVIEW,
      loadEvents: async () => EVENTS,
      loadPois: async () => POIS,
    });

    expect(result).toEqual({
      trip: TRIP,
      preview: PREVIEW,
      events: EVENTS,
      pois: POIS,
      warning: null,
    });
  });

  it("keeps the previous POI list when the optional POI request fails", async () => {
    const previousPois: PoiSummary[] = [
      {
        id: 9,
        name: "Cached POI",
        lat: 35.0,
        lng: 139.8,
        google_place_id: null,
        primary_category: "lunch",
        is_active: true,
      },
    ];

    const result = await loadActiveTripBootstrap(
      {
        loadTrip: async () => TRIP,
        loadPreview: async () => PREVIEW,
        loadEvents: async () => EVENTS,
        loadPois: async () => {
          throw new Error("pois unavailable");
        },
      },
      previousPois,
    );

    expect(result.pois).toEqual(previousPois);
    expect(result.warning).toBe(ACTIVE_TRIP_POIS_UNAVAILABLE_MESSAGE);
  });

  it("rejects when a required request fails", async () => {
    await expect(
      loadActiveTripBootstrap({
        loadTrip: async () => TRIP,
        loadPreview: async () => {
          throw new Error("preview unavailable");
        },
        loadEvents: async () => EVENTS,
        loadPois: async () => POIS,
      }),
    ).rejects.toThrow("preview unavailable");
  });
});
