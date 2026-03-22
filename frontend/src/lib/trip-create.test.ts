import { describe, expect, it } from "vitest";
import {
  buildTripCreatePayload,
  resolveDefaultMustVisitPoiIds,
} from "@/lib/trip-create";

describe("buildTripCreatePayload", () => {
  it("keeps an empty must-visit list when defaults are deselected", () => {
    const payload = buildTripCreatePayload(
      {
        planDate: "2026-03-22",
        originLabel: "Start",
        originLat: "35.727",
        originLng: "139.791",
        destLabel: "End",
        destLat: "35.727",
        destLng: "139.791",
        departureStart: "08:00",
        departureEnd: "09:00",
        returnDeadline: "01:00",
        weatherMode: "normal",
        drivingPenaltyWeight: 0.08,
        maxContinuousDriveMinutes: 90,
        mustHaveCafe: true,
        budgetBand: "premium",
        paceStyle: "packed",
      },
      [],
      [4],
      ["seafood", "quick"],
      ["romantic"],
    );

    expect(payload.initial_must_visit_poi_ids).toEqual([]);
    expect(payload.initial_excluded_poi_ids).toEqual([4]);
    expect(payload.return_deadline_min).toBe(25 * 60);
    expect(payload.preferences).toEqual({
      driving_penalty_weight: 0.08,
      max_continuous_drive_minutes: 90,
      preferred_lunch_tags: ["seafood", "quick"],
      preferred_dinner_tags: ["romantic"],
      must_have_cafe: true,
      budget_band: "premium",
      pace_style: "packed",
    });
  });
});

describe("resolveDefaultMustVisitPoiIds", () => {
  it("keeps only default POIs that exist in the loaded list", () => {
    expect(
      resolveDefaultMustVisitPoiIds([{ id: 7 }, { id: 9 }, { id: 1 }]),
    ).toEqual([1, 7]);
  });

  it("returns an empty list when no default POIs are available", () => {
    expect(resolveDefaultMustVisitPoiIds([])).toEqual([]);
    expect(resolveDefaultMustVisitPoiIds([{ id: 9 }, { id: 10 }])).toEqual([]);
  });
});
