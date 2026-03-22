import { describe, expect, it } from "vitest";
import { buildTripCreatePayload } from "@/lib/trip-create";

describe("buildTripCreatePayload", () => {
  it("builds the new trip frame payload", () => {
    const payload = buildTripCreatePayload({
      title: "休日ドライブ",
      planDate: "2026-03-22",
      timezone: "Asia/Tokyo",
      originLabel: "自宅",
      originLat: "35.72",
      originLng: "139.79",
      destinationLabel: "ホテル",
      destinationLat: "35.45",
      destinationLng: "139.92",
      departureStart: "08:00",
      departureEnd: "09:00",
      endMinute: "21:00",
      endKind: "arrive_by",
      weather: "rain",
    });

    expect(payload).toEqual({
      title: "休日ドライブ",
      plan_date: "2026-03-22",
      origin: { label: "自宅", lat: 35.72, lng: 139.79 },
      destination: { label: "ホテル", lat: 35.45, lng: 139.92 },
      departure_window_start_min: 480,
      departure_window_end_min: 540,
      end_constraint: { kind: "arrive_by", minute_of_day: 1260 },
      timezone: "Asia/Tokyo",
      context: { weather: "rain", traffic_profile: "default" },
    });
  });
});
