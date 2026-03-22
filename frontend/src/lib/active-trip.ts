import type {
  EventOut,
  PlannedStopOut,
  PoiSummary,
  RoutePreviewOut,
  TripDetailOut,
} from "@/lib/types";

export type ActiveTripState = {
  completedPoiIds: number[];
  inProgressPoiId: number | null;
  currentStop: PlannedStopOut | null;
  nextStop: PlannedStopOut | null;
};

export const ACTIVE_TRIP_POIS_UNAVAILABLE_MESSAGE =
  "POI catalog is temporarily unavailable. Route details are still loaded.";

type ActiveTripBootstrapLoaders = {
  loadTrip: () => Promise<TripDetailOut>;
  loadPreview: () => Promise<RoutePreviewOut>;
  loadEvents: () => Promise<EventOut[]>;
  loadPois: () => Promise<PoiSummary[]>;
};

export type ActiveTripBootstrapResult = {
  trip: TripDetailOut;
  preview: RoutePreviewOut;
  events: EventOut[];
  pois: PoiSummary[];
  warning: string | null;
};

function stopIndexByPoiId(stops: PlannedStopOut[], poiId: number | null): number {
  if (poiId === null) {
    return -1;
  }
  return stops.findIndex((stop) => stop.poi_id === poiId);
}

function firstRemainingPoiStop(
  stops: PlannedStopOut[],
  completedPoiIds: number[],
  excludePoiId: number | null = null,
): PlannedStopOut | null {
  return (
    stops.find((stop) => {
      if (stop.node_kind !== "poi" || stop.poi_id === null) {
        return false;
      }
      if (excludePoiId !== null && stop.poi_id === excludePoiId) {
        return false;
      }
      return !completedPoiIds.includes(stop.poi_id);
    }) || null
  );
}

export function resolveDisplayedCurrentStop(
  activeState: Pick<ActiveTripState, "inProgressPoiId" | "currentStop">,
  fallbackCurrentStop: PlannedStopOut | null,
): PlannedStopOut | null {
  if (activeState.currentStop !== null) {
    return activeState.currentStop;
  }
  if (activeState.inProgressPoiId === null) {
    return null;
  }
  if (fallbackCurrentStop?.poi_id === activeState.inProgressPoiId) {
    return fallbackCurrentStop;
  }
  return null;
}

export function deriveActiveTripState(
  stops: PlannedStopOut[],
  events: EventOut[],
): ActiveTripState {
  const completedPoiIds: number[] = [];
  let inProgressPoiId: number | null = null;

  for (const event of events) {
    const poiId = Number(event.payload_json?.poi_id || 0) || null;
    if (event.event_type === "arrived") {
      inProgressPoiId = poiId;
    } else if (event.event_type === "departed") {
      if (inProgressPoiId !== null) {
        completedPoiIds.push(inProgressPoiId);
      }
      inProgressPoiId = null;
    } else if (event.event_type === "skipped" && poiId !== null) {
      completedPoiIds.push(poiId);
      if (inProgressPoiId === poiId) {
        inProgressPoiId = null;
      }
    }
  }

  const poiStops = stops.filter((stop) => stop.node_kind === "poi");
  const currentStop =
    inProgressPoiId !== null
      ? poiStops.find((stop) => stop.poi_id === inProgressPoiId) || null
      : firstRemainingPoiStop(poiStops, completedPoiIds);

  let nextStop: PlannedStopOut | null = null;
  if (inProgressPoiId !== null) {
    const currentIndex =
      currentStop === null ? -1 : stopIndexByPoiId(stops, currentStop.poi_id);
    nextStop =
      currentIndex >= 0
        ? stops.slice(currentIndex + 1).find((stop) => stop.node_kind === "poi") || null
        : firstRemainingPoiStop(poiStops, completedPoiIds, inProgressPoiId);
  } else {
    const currentIndex =
      currentStop === null ? -1 : stopIndexByPoiId(stops, currentStop.poi_id);
    nextStop =
      currentIndex >= 0
        ? stops.slice(currentIndex + 1).find((stop) => stop.node_kind === "poi") || null
        : null;
  }

  return {
    completedPoiIds,
    inProgressPoiId,
    currentStop,
    nextStop,
  };
}

export async function loadActiveTripBootstrap(
  loaders: ActiveTripBootstrapLoaders,
  previousPois: PoiSummary[] = [],
): Promise<ActiveTripBootstrapResult> {
  const [tripResult, previewResult, eventsResult, poisResult] =
    await Promise.allSettled([
      loaders.loadTrip(),
      loaders.loadPreview(),
      loaders.loadEvents(),
      loaders.loadPois(),
    ]);

  if (tripResult.status === "rejected") {
    throw tripResult.reason;
  }
  if (previewResult.status === "rejected") {
    throw previewResult.reason;
  }
  if (eventsResult.status === "rejected") {
    throw eventsResult.reason;
  }

  return {
    trip: tripResult.value,
    preview: previewResult.value,
    events: eventsResult.value,
    pois: poisResult.status === "fulfilled" ? poisResult.value : previousPois,
    warning:
      poisResult.status === "fulfilled"
        ? null
        : ACTIVE_TRIP_POIS_UNAVAILABLE_MESSAGE,
  };
}
