import { describe, expect, it } from "vitest";
import { loadActiveTripBootstrap } from "@/lib/active-trip";
import type { ActiveTripBootstrapOut } from "@/lib/types";

describe("loadActiveTripBootstrap strictness", () => {
  it("does not reconstruct or infer any active-trip state client-side", async () => {
    const bootstrap: ActiveTripBootstrapOut = {
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
      events: [],
      pois: [],
      active_state: {
        completed_poi_ids: [],
        in_progress_poi_id: null,
        current_stop: null,
        next_stop: null,
      },
    };

    await expect(loadActiveTripBootstrap(async () => bootstrap)).resolves.toEqual(
      bootstrap,
    );
  });
});
