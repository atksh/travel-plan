import type { SolvePayload } from "@/lib/types";

export function formatMinute(minute: number | null | undefined): string {
  if (minute === null || minute === undefined) {
    return "--:--";
  }
  const normalized = ((minute % (24 * 60)) + 24 * 60) % (24 * 60);
  const hours = String(Math.floor(normalized / 60)).padStart(2, "0");
  const minutes = String(normalized % 60).padStart(2, "0");
  return `${hours}:${minutes}`;
}

export function formatDuration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) {
    return "--";
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours > 0 && rest > 0) {
    return `${hours}時間${rest}分`;
  }
  if (hours > 0) {
    return `${hours}時間`;
  }
  return `${rest}分`;
}

export function formatDistance(meters: number): string {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)}km`;
  }
  return `${meters}m`;
}

export function dateInputValue(now: Date = new Date()): string {
  const year = String(now.getFullYear());
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function timeInputValue(minutes: number): string {
  const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
  const rest = String(minutes % 60).padStart(2, "0");
  return `${hours}:${rest}`;
}

export function timeInputToMinute(value: string): number {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

export function summarizeSolveDiff(
  accepted: SolvePayload | null,
  compared: SolvePayload | null,
): string {
  if (!accepted || !compared) {
    return "比較対象がありません。";
  }
  const driveDelta = compared.summary.total_drive_minutes - accepted.summary.total_drive_minutes;
  const stopDelta = compared.selected_place_ids.length - accepted.selected_place_ids.length;
  return `運転時間 ${driveDelta >= 0 ? "+" : ""}${driveDelta}分 / 立ち寄り ${stopDelta >= 0 ? "+" : ""}${stopDelta}件`;
}
