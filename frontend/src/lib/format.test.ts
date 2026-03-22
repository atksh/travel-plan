import { describe, expect, it } from "vitest";
import { formatDuration, formatMinute, summarizeSolveDiff } from "@/lib/format";
import type { SolvePayload } from "@/lib/types";

const SOLVE_A: SolvePayload = {
  summary: {
    feasible: true,
    score: 10,
    total_drive_minutes: 120,
    total_stay_minutes: 180,
    total_distance_meters: 40000,
    start_time_min: 480,
    end_time_min: 900,
  },
  stops: [],
  route_legs: [],
  selected_place_ids: [1, 2],
  unselected_candidates: [],
  rule_results: [],
  warnings: [],
  alternatives: [],
};

const SOLVE_B: SolvePayload = {
  ...SOLVE_A,
  summary: { ...SOLVE_A.summary, total_drive_minutes: 135 },
  selected_place_ids: [1, 2, 3],
};

describe("format helpers", () => {
  it("formats minutes to HH:mm", () => {
    expect(formatMinute(540)).toBe("09:00");
  });

  it("formats durations in Japanese", () => {
    expect(formatDuration(135)).toBe("2時間15分");
    expect(formatDuration(45)).toBe("45分");
  });

  it("summarizes solve differences", () => {
    expect(summarizeSolveDiff(SOLVE_A, SOLVE_B)).toContain("+15分");
    expect(summarizeSolveDiff(SOLVE_A, SOLVE_B)).toContain("+1件");
  });
});
