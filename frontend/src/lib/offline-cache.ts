import { useEffect, useState } from "react";
import type { PoiSummary, SolveResponse, TripDetailOut } from "@/lib/types";

const CACHE_PREFIX = "bosodrive:trip-cache:";

type CachedPlan = {
  trip: TripDetailOut;
  solve: SolveResponse | null;
  pois: PoiSummary[];
  cachedAt: string;
};

export function savePlanCache(
  tripId: string,
  payload: Omit<CachedPlan, "cachedAt">,
) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(
    `${CACHE_PREFIX}${tripId}`,
    JSON.stringify({
      ...payload,
      cachedAt: new Date().toISOString(),
    } satisfies CachedPlan),
  );
}

export function loadPlanCache(tripId: string): CachedPlan | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(`${CACHE_PREFIX}${tripId}`);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as CachedPlan;
  } catch {
    return null;
  }
}

export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    const updateOnlineStatus = () => setIsOnline(window.navigator.onLine);
    updateOnlineStatus();
    window.addEventListener("online", updateOnlineStatus);
    window.addEventListener("offline", updateOnlineStatus);
    return () => {
      window.removeEventListener("online", updateOnlineStatus);
      window.removeEventListener("offline", updateOnlineStatus);
    };
  }, []);

  return isOnline;
}
