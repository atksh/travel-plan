import { describe, expect, it } from "vitest";
import { loadActiveTripBootstrap } from "@/lib/active-trip";
import type { ActiveTripBootstrapOut } from "@/lib/types";

const BOOTSTRAP: ActiveTripBootstrapOut = {
  trip: {
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
    latest_solve: null,
  },
  events: [
    {
      id: 1,
      event_type: "arrived",
      payload_json: { poi_id: 7 },
      recorded_at: "2026-03-21T00:00:00Z",
    },
  ],
  pois: [
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
  active_state: {
    completed_poi_ids: [],
    in_progress_poi_id: 7,
    current_stop: null,
    next_stop: null,
  },
};

describe("loadActiveTripBootstrap", () => {
  it("returns the canonical bootstrap payload unchanged", async () => {
    const result = await loadActiveTripBootstrap(async () => BOOTSTRAP);

    expect(result).toEqual(BOOTSTRAP);
  });

  it("rejects when the canonical bootstrap request fails", async () => {
    await expect(
      loadActiveTripBootstrap(async () => {
        throw new Error("bootstrap unavailable");
      }),
    ).rejects.toThrow("bootstrap unavailable");
  });
});
