import { timeInputToMinute, timeInputValue } from "@/lib/format";
import type { PoiSummary } from "@/lib/types";

export const DEFAULT_MUST_VISIT_POI_IDS = [1, 7] as const;

export type TripCreateFormState = {
  planDate: string;
  originLabel: string;
  originLat: string;
  originLng: string;
  destLabel: string;
  destLat: string;
  destLng: string;
  departureStart: string;
  departureEnd: string;
  returnDeadline: string;
  weatherMode: string;
  drivingPenaltyWeight: number;
  maxContinuousDriveMinutes: number;
  mustHaveCafe: boolean;
  budgetBand: string;
  paceStyle: string;
};

export type TripCreatePreferencesPayload = {
  driving_penalty_weight: number;
  max_continuous_drive_minutes: number;
  preferred_lunch_tags: string[];
  preferred_dinner_tags: string[];
  must_have_cafe: boolean;
  budget_band: string | null;
  pace_style: string;
};

export type TripCreatePayload = {
  plan_date: string;
  origin_lat: number;
  origin_lng: number;
  origin_label: string;
  dest_lat: number;
  dest_lng: number;
  dest_label: string;
  departure_window_start_min: number;
  departure_window_end_min: number;
  return_deadline_min: number;
  weather_mode: string;
  initial_must_visit_poi_ids: number[];
  initial_excluded_poi_ids: number[];
  preferences: TripCreatePreferencesPayload;
};

export type SuggestedTripFrame = {
  planDate: string;
  departureStart: string;
  departureEnd: string;
  returnDeadline: string;
};

type TokyoDateParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

function orderedUniquePoiIds(poiIds: number[]): number[] {
  return Array.from(new Set(poiIds));
}

export function buildSuggestedTripFrame(now: Date = new Date()): SuggestedTripFrame {
  const departureStartMinute = 8 * 60;
  const departureEndMinute = 9 * 60;
  const returnDeadlineMinute = 25 * 60;
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(now);
  const tokyoParts = Object.fromEntries(
    parts
      .filter((part) =>
        ["year", "month", "day", "hour", "minute"].includes(part.type),
      )
      .map((part) => [part.type, Number(part.value)]),
  ) as TokyoDateParts;
  const currentMinute = tokyoParts.hour * 60 + tokyoParts.minute;
  const planDate = new Date(
    Date.UTC(tokyoParts.year, tokyoParts.month - 1, tokyoParts.day),
  );
  if (currentMinute >= departureStartMinute) {
    planDate.setUTCDate(planDate.getUTCDate() + 1);
  }
  return {
    planDate: planDate.toISOString().slice(0, 10),
    departureStart: timeInputValue(departureStartMinute),
    departureEnd: timeInputValue(departureEndMinute),
    returnDeadline: timeInputValue(returnDeadlineMinute % (24 * 60)),
  };
}

export function resolveDefaultMustVisitPoiIds(
  pois: Pick<PoiSummary, "id">[],
  defaultPoiIds: readonly number[] = DEFAULT_MUST_VISIT_POI_IDS,
): number[] {
  const availablePoiIds = new Set(pois.map((poi) => poi.id));
  return defaultPoiIds.filter((poiId) => availablePoiIds.has(poiId));
}

export function buildTripCreatePayload(
  form: TripCreateFormState,
  mustVisitIds: number[],
  excludeIds: number[],
  preferredLunchTags: string[],
  preferredDinnerTags: string[],
): TripCreatePayload {
  const returnDeadlineMinute = timeInputToMinute(form.returnDeadline);
  return {
    plan_date: form.planDate,
    origin_lat: Number(form.originLat),
    origin_lng: Number(form.originLng),
    origin_label: form.originLabel,
    dest_lat: Number(form.destLat),
    dest_lng: Number(form.destLng),
    dest_label: form.destLabel,
    departure_window_start_min: timeInputToMinute(form.departureStart),
    departure_window_end_min: timeInputToMinute(form.departureEnd),
    return_deadline_min:
      returnDeadlineMinute < 6 * 60
        ? returnDeadlineMinute + 24 * 60
        : returnDeadlineMinute,
    weather_mode: form.weatherMode,
    initial_must_visit_poi_ids: orderedUniquePoiIds(mustVisitIds),
    initial_excluded_poi_ids: orderedUniquePoiIds(excludeIds),
    preferences: {
      driving_penalty_weight: form.drivingPenaltyWeight,
      max_continuous_drive_minutes: form.maxContinuousDriveMinutes,
      preferred_lunch_tags: preferredLunchTags,
      preferred_dinner_tags: preferredDinnerTags,
      must_have_cafe: form.mustHaveCafe,
      budget_band: form.budgetBand || null,
      pace_style: form.paceStyle,
    },
  };
}
