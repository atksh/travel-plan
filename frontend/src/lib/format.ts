const FALLBACK_MESSAGES: Record<string, string> = {
  no_lunch_candidate: "No lunch spot is available in the current candidate set.",
  no_dinner_candidate: "No dinner spot is available in the current candidate set.",
  no_sweets_candidate: "No cafe or sweets spot is available in the current candidate set.",
  no_sunset_candidate: "No sunset candidate remains in the shortlist.",
  no_feasible_route: "The current constraints do not allow a feasible route.",
  rain_mode_removed_outdoor_candidates:
    "Rain mode removed outdoor spots from the remaining graph.",
  heuristic_fallback: "A fast fallback solve path was used for this graph.",
  cbc_timeout: "The MIP solver timed out and fell back to a simpler route search.",
};

export function formatMinute(minute: number | null | undefined): string {
  if (minute === null || minute === undefined) {
    return "--:--";
  }
  const normalized = ((minute % (24 * 60)) + 24 * 60) % (24 * 60);
  const hours = String(Math.floor(normalized / 60)).padStart(2, "0");
  const minutes = String(normalized % 60).padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function formatDuration(minute: number | null | undefined): string {
  if (minute === null || minute === undefined) {
    return "--";
  }
  const hours = Math.floor(minute / 60);
  const minutes = minute % 60;
  if (hours > 0 && minutes > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (hours > 0) {
    return `${hours}h`;
  }
  return `${minutes}m`;
}

export function humanizeReason(code: string): string {
  if (FALLBACK_MESSAGES[code]) {
    return FALLBACK_MESSAGES[code];
  }
  if (code.startsWith("must_visit_")) {
    return `A must-visit stop became infeasible: ${code.replaceAll("_", " ")}`;
  }
  return code.replaceAll("_", " ");
}

export function localDateInputValue(date: Date = new Date()): string {
  const year = String(date.getFullYear());
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function timeInputValue(minute: number): string {
  const hours = String(Math.floor(minute / 60)).padStart(2, "0");
  const minutes = String(minute % 60).padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function timeInputToMinute(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

export function groupCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    lunch: "Lunch",
    dinner: "Dinner",
    sweets: "Cafe / Sweets",
    sunset: "Sunset",
    healing: "Healing",
    sightseeing_active: "Active sightseeing",
    sightseeing_relax: "Relaxed sightseeing",
    hub: "Hub / indoor fallback",
  };
  return labels[category] || category;
}

export function appleMapsHref(
  fromLat: number,
  fromLng: number,
  toLat: number,
  toLng: number,
): string {
  return `https://maps.apple.com/?saddr=${fromLat},${fromLng}&daddr=${toLat},${toLng}&dirflg=d`;
}

export function googleMapsHref(
  fromLat: number,
  fromLng: number,
  toLat: number,
  toLng: number,
): string {
  return `https://www.google.com/maps/dir/?api=1&origin=${fromLat},${fromLng}&destination=${toLat},${toLng}&travelmode=driving`;
}
