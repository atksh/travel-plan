import { timeInputToMinute } from "@/lib/format";

export type TripCreateFormState = {
  title: string;
  planDate: string;
  timezone: string;
  originLabel: string;
  originLat: string;
  originLng: string;
  destinationLabel: string;
  destinationLat: string;
  destinationLng: string;
  departureStart: string;
  departureEnd: string;
  endMinute: string;
  endKind: string;
  weather: string;
};

export function buildTripCreatePayload(form: TripCreateFormState) {
  return {
    title: form.title,
    plan_date: form.planDate,
    origin: {
      label: form.originLabel,
      lat: Number(form.originLat),
      lng: Number(form.originLng),
    },
    destination: {
      label: form.destinationLabel,
      lat: Number(form.destinationLat),
      lng: Number(form.destinationLng),
    },
    departure_window_start_min: timeInputToMinute(form.departureStart),
    departure_window_end_min: timeInputToMinute(form.departureEnd),
    end_constraint: {
      kind: form.endKind,
      minute_of_day: timeInputToMinute(form.endMinute),
    },
    timezone: form.timezone,
    context: {
      weather: form.weather || null,
      traffic_profile: "default",
    },
  };
}
