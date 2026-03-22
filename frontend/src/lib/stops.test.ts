import { describe, expect, it } from "vitest";
import { stopToPoint } from "@/lib/stops";
import type { PlannedStopOut } from "@/lib/types";

describe("stopToPoint", () => {
  it("maps a strict planned stop contract directly into a point", () => {
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

    expect(stopToPoint(stop)).toEqual({
      lat: 35.15,
      lng: 139.84,
      label: "Current location",
    });
  });
});
