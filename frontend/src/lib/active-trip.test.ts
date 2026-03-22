import { describe, expect, it } from "vitest";
import {
  deriveActiveTripState,
  resolveDisplayedCurrentStop,
} from "@/lib/active-trip";
import type { EventOut, PlannedStopOut } from "@/lib/types";

const REPLAN_STOPS: PlannedStopOut[] = [
  {
    sequence_order: 0,
    poi_id: null,
    poi_name: "Start",
    node_kind: "start",
    arrival_min: 480,
    departure_min: 480,
    stay_min: 0,
    leg_from_prev_min: null,
    status: "planned",
  },
  {
    sequence_order: 1,
    poi_id: 2,
    poi_name: "Next stop",
    node_kind: "poi",
    arrival_min: 660,
    departure_min: 720,
    stay_min: 60,
    leg_from_prev_min: 30,
    status: "planned",
  },
];

const CURRENT_STOP: PlannedStopOut = {
  sequence_order: 1,
  poi_id: 1,
  poi_name: "Current stop",
  node_kind: "poi",
  arrival_min: 540,
  departure_min: 600,
  stay_min: 60,
  leg_from_prev_min: 45,
  status: "planned",
};

function arrivedEvent(poiId: number): EventOut {
  return {
    id: 1,
    event_type: "arrived",
    payload_json: { poi_id: poiId },
    recorded_at: "2026-03-21T00:00:00Z",
  };
}

function departedEvent(): EventOut {
  return {
    id: 2,
    event_type: "departed",
    payload_json: null,
    recorded_at: "2026-03-21T00:10:00Z",
  };
}

describe("deriveActiveTripState", () => {
  it("keeps the next stop when the in-progress POI is absent from replanned stops", () => {
    const state = deriveActiveTripState(REPLAN_STOPS, [arrivedEvent(1)]);

    expect(state.inProgressPoiId).toBe(1);
    expect(state.currentStop).toBeNull();
    expect(state.nextStop?.poi_id).toBe(2);
  });
});

describe("resolveDisplayedCurrentStop", () => {
  it("falls back to the last known current stop during an in-progress replan", () => {
    const activeState = deriveActiveTripState(REPLAN_STOPS, [arrivedEvent(1)]);

    expect(resolveDisplayedCurrentStop(activeState, CURRENT_STOP)).toEqual(CURRENT_STOP);
  });

  it("clears the fallback once in-progress state is gone", () => {
    const activeState = deriveActiveTripState(REPLAN_STOPS, [
      arrivedEvent(1),
      departedEvent(),
    ]);

    expect(activeState.inProgressPoiId).toBeNull();
    expect(resolveDisplayedCurrentStop(activeState, CURRENT_STOP)?.poi_id).toBe(2);
  });
});
