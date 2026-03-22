"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  appleMapsHref,
  formatMinute,
  googleMapsHref,
  humanizeReason,
} from "@/lib/format";
import { loadActiveTripBootstrap } from "@/lib/active-trip";
import { api } from "@/lib/api";
import { useOnlineStatus } from "@/lib/offline-cache";
import { requiresDiningCategoryChoice } from "@/lib/poi-import";
import { stopToPoint } from "@/lib/stops";
import type {
  ActiveTripBootstrapOut,
  PoiSummary,
  SolveResponse,
} from "@/lib/types";

type SearchResult = {
  place_id: string;
  displayName: { text: string };
  primaryType: string;
  location: { latitude: number; longitude: number };
};

function MapButtons({
  currentPoint,
  nextPoint,
}: {
  currentPoint: { lat: number; lng: number } | null;
  nextPoint: { lat: number; lng: number } | null;
}) {
  if (!currentPoint || !nextPoint) {
    return null;
  }
  return (
    <div className="button-row" style={{ marginTop: "1rem" }}>
      {[
        { label: "Open Apple Maps", hrefBuilder: appleMapsHref },
        { label: "Open Google Maps", hrefBuilder: googleMapsHref },
      ].map(({ label, hrefBuilder }) => (
        <a
          key={label}
          className="small-button"
          href={hrefBuilder(
            currentPoint.lat,
            currentPoint.lng,
            nextPoint.lat,
            nextPoint.lng,
          )}
          rel="noreferrer"
          target="_blank"
        >
          {label}
        </a>
      ))}
    </div>
  );
}

export default function ActiveTripPage() {
  const params = useParams();
  const tripId = String(params.id);
  const [bootstrap, setBootstrap] = useState<ActiveTripBootstrapOut | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [lastReplan, setLastReplan] = useState<SolveResponse | null>(null);
  const isOnline = useOnlineStatus();

  const refresh = useCallback(async () => {
    try {
      const nextBootstrap = await loadActiveTripBootstrap(() =>
        api<ActiveTripBootstrapOut>(`/api/trips/${tripId}/active-bootstrap`),
      );
      setBootstrap(nextBootstrap);
      setError(null);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Refresh failed");
      throw refreshError;
    }
  }, [tripId]);

  useEffect(() => {
    void refresh().catch((refreshError) => {
      setError(refreshError instanceof Error ? refreshError.message : "Refresh failed");
    });
  }, [refresh]);

  const trip = bootstrap?.trip ?? null;
  const pois = bootstrap?.pois ?? [];
  const activeState = bootstrap?.active_state ?? {
    completed_poi_ids: [],
    in_progress_poi_id: null,
    current_stop: null,
    next_stop: null,
  };
  const currentPoint = activeState.current_stop
    ? stopToPoint(activeState.current_stop)
    : null;
  const nextPoint = activeState.next_stop ? stopToPoint(activeState.next_stop) : null;
  const removableCandidates =
    trip?.candidates.filter(
      (candidate) => !activeState.completed_poi_ids.includes(candidate.poi_id),
    ) ?? [];
  const localMatches = searchTerm
    ? pois.filter((poi) => poi.name.toLowerCase().includes(searchTerm.toLowerCase())).slice(0, 5)
    : [];

  async function requestCurrentLocation(): Promise<Record<string, number>> {
    if (!navigator.geolocation) {
      throw new Error("Geolocation is not available in this browser.");
    }
    return new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(
        (position) =>
          resolve({
            current_lat: position.coords.latitude,
            current_lng: position.coords.longitude,
          }),
        () => reject(new Error("Unable to retrieve current location.")),
        { enableHighAccuracy: true, timeout: 10000 },
      );
    });
  }

  async function postLifecycleEvent(eventType: "arrived" | "departed" | "skipped") {
    const targetPoiId =
      eventType === "departed"
        ? activeState.in_progress_poi_id
        : activeState.current_stop?.poi_id;
    if (!targetPoiId) {
      setError("No target stop is available for this action.");
      return;
    }
    setBusy(eventType);
    setError(null);
    try {
      await api(`/api/trips/${tripId}/events`, {
        method: "POST",
        body: JSON.stringify({ event_type: eventType, payload: { poi_id: targetPoiId } }),
      });
      await refresh();
      setNote(`Sent ${eventType} for stop ${targetPoiId}.`);
    } catch (eventError) {
      setError(eventError instanceof Error ? eventError.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  async function runReplan() {
    setBusy("replan");
    setError(null);
    try {
      const locationBody = await requestCurrentLocation();
      const response = await api<SolveResponse>(`/api/trips/${tripId}/replan`, {
        method: "POST",
        body: JSON.stringify(locationBody),
      });
      setLastReplan(response);
      await refresh();
      setNote(
        response.alternatives.length > 0
          ? `Replanned. Alternatives: ${response.alternatives
              .map((candidate) => candidate.poi_name)
              .join(", ")}`
          : `Replanned route. Feasible: ${String(response.feasible)}`,
      );
    } catch (replanError) {
      setError(replanError instanceof Error ? replanError.message : "Replan failed");
    } finally {
      setBusy(null);
    }
  }

  async function toggleWeatherMode() {
    if (!trip) {
      return;
    }
    const nextWeatherMode = trip.weather_mode === "rain" ? "normal" : "rain";
    setBusy("weather");
    setError(null);
    try {
      await api(`/api/trips/${tripId}`, {
        method: "PATCH",
        body: JSON.stringify({ weather_mode: nextWeatherMode }),
      });
      await refresh();
      setNote(`Weather mode switched to ${nextWeatherMode}.`);
    } catch (weatherError) {
      setError(weatherError instanceof Error ? weatherError.message : "Weather update failed");
    } finally {
      setBusy(null);
    }
  }

  async function searchPlaces() {
    if (!searchTerm.trim()) {
      setSearchResults([]);
      return;
    }
    setBusy("search");
    setError(null);
    try {
      const response = await api<{ results: SearchResult[] }>("/api/pois/search", {
        method: "POST",
        body: JSON.stringify({ query: searchTerm, region: "jp" }),
      });
      setSearchResults(response.results);
    } catch (searchError) {
      setError(searchError instanceof Error ? searchError.message : "Search failed");
    } finally {
      setBusy(null);
    }
  }

  async function addExistingSpot(poiId: number) {
    if (!trip) {
      return;
    }
    setBusy(`add-${poiId}`);
    setError(null);
    try {
      const existing = trip.candidates.find((candidate) => candidate.poi_id === poiId);
      if (existing) {
        await api(`/api/trips/${tripId}/candidates/${existing.id}`, {
          method: "PATCH",
          body: JSON.stringify({ excluded: false, locked_out: false }),
        });
      } else {
        await api(`/api/trips/${tripId}/candidates`, {
          method: "POST",
          body: JSON.stringify({ poi_id: poiId }),
        });
      }
      await runReplan();
    } catch (addError) {
      setError(addError instanceof Error ? addError.message : "Add spot failed");
    } finally {
      setBusy(null);
    }
  }

  async function addRemoteSpot(
    result: SearchResult,
    categoryOverride?: "lunch" | "dinner",
  ) {
    setBusy(`import-${result.place_id}${categoryOverride ? `-${categoryOverride}` : ""}`);
    setError(null);
    try {
      const imported = await api<PoiSummary & { id: number }>("/api/pois/import", {
        method: "POST",
        body: JSON.stringify({
          place_id: result.place_id,
          display_name: result.displayName.text,
          category_override: categoryOverride ?? null,
        }),
      });
      await addExistingSpot(imported.id);
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : "Import failed");
      setBusy(null);
    }
  }

  async function removeCandidate(candidateId: number) {
    setBusy(`remove-${candidateId}`);
    setError(null);
    try {
      await api(`/api/trips/${tripId}/candidates/${candidateId}`, { method: "DELETE" });
      await runReplan();
    } catch (removeError) {
      setError(removeError instanceof Error ? removeError.message : "Remove failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Active trip</span>
            <h1>Foreground mode for day-of replanning.</h1>
            <p>
              Use the buttons when you arrive, depart, skip, or need to rebuild the
              remaining route from your current position.
            </p>
          </div>
          <div className="summary-row">
            <div className="summary-pill">
              <span>Weather</span>
              <strong>{trip?.weather_mode ?? "--"}</strong>
            </div>
            <div className="summary-pill">
              <span>Completed</span>
              <strong>{activeState.completed_poi_ids.length}</strong>
            </div>
            {!isOnline ? <div className="offline-badge">Offline actions disabled</div> : null}
          </div>
        </section>

        {error ? <p className="error-text">{error}</p> : null}
        {note ? <p className="muted-text">{note}</p> : null}

        <div className="two-column">
          <section className="panel">
            <div className="section-heading">
              <h2>Current stop</h2>
              <p>The stop you should be at now, based on the route and event history.</p>
            </div>
            <div className="stack">
              <article className="candidate-item">
                <div className="candidate-title">
                  {activeState.current_stop?.poi_name || "No current stop"}
                </div>
                <div className="timeline-meta">
                  {activeState.current_stop
                    ? `${formatMinute(activeState.current_stop.arrival_min)} - ${formatMinute(activeState.current_stop.departure_min)}`
                    : "The route may still be empty."}
                </div>
              </article>
              <article className="candidate-item">
                <div className="candidate-title">
                  {activeState.next_stop?.poi_name || "No next stop"}
                </div>
                <div className="timeline-meta">
                  {activeState.next_stop
                    ? `Next ETA ${formatMinute(activeState.next_stop.arrival_min)}`
                    : "Nothing queued after the current stop."}
                </div>
              </article>
            </div>
            <div className="button-row" style={{ marginTop: "1rem" }}>
              <button
                className="primary-button"
                disabled={
                  !isOnline ||
                  busy !== null ||
                  activeState.current_stop === null ||
                  activeState.in_progress_poi_id !== null
                }
                type="button"
                onClick={() => void postLifecycleEvent("arrived")}
              >
                Arrived
              </button>
              <button
                className="secondary-button"
                disabled={!isOnline || busy !== null || activeState.in_progress_poi_id === null}
                type="button"
                onClick={() => void postLifecycleEvent("departed")}
              >
                Departed
              </button>
              <button
                className="secondary-button"
                disabled={!isOnline || busy !== null || activeState.current_stop === null}
                type="button"
                onClick={() => void postLifecycleEvent("skipped")}
              >
                Skip
              </button>
              <button
                className="secondary-button"
                disabled={!isOnline || busy !== null}
                type="button"
                onClick={() => void toggleWeatherMode()}
              >
                {trip?.weather_mode === "rain" ? "Back to normal" : "Rain mode"}
              </button>
              <button
                className="primary-button"
                disabled={!isOnline || busy !== null}
                type="button"
                onClick={() => void runReplan()}
              >
                Replan
              </button>
            </div>
            <MapButtons currentPoint={currentPoint} nextPoint={nextPoint} />
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Add spot</h2>
              <p>Search local candidates or import a Google Places result into this trip.</p>
            </div>
            <div className="button-row">
              <input
                placeholder="Search place name"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
              />
              <button
                className="secondary-button"
                disabled={!isOnline || busy === "search"}
                type="button"
                onClick={() => void searchPlaces()}
              >
                Search
              </button>
            </div>
            <div className="stack" style={{ marginTop: "1rem" }}>
              {localMatches.map((poi) => (
                <article key={poi.id} className="candidate-item">
                  <div className="candidate-title">{poi.name}</div>
                  <div className="timeline-meta">{poi.primary_category}</div>
                  <button
                    className="small-button"
                    disabled={!isOnline || busy === `add-${poi.id}`}
                    type="button"
                    onClick={() => void addExistingSpot(poi.id)}
                  >
                    Add local spot
                  </button>
                </article>
              ))}
              {searchResults.map((result) => {
                const needsChoice = requiresDiningCategoryChoice(result.primaryType);
                const importing = busy?.startsWith(`import-${result.place_id}`) === true;
                return (
                  <article key={result.place_id} className="candidate-item">
                    <div className="candidate-title">
                      {result.displayName.text}
                    </div>
                    <div className="timeline-meta">
                      {needsChoice
                        ? "Google Places result: choose lunch or dinner"
                        : "Google Places result"}
                    </div>
                    {needsChoice ? (
                      <div className="button-row" style={{ marginTop: "0.75rem" }}>
                        <button
                          className="small-button"
                          disabled={!isOnline || importing}
                          type="button"
                          onClick={() => void addRemoteSpot(result, "lunch")}
                        >
                          Import as lunch
                        </button>
                        <button
                          className="small-button"
                          disabled={!isOnline || importing}
                          type="button"
                          onClick={() => void addRemoteSpot(result, "dinner")}
                        >
                          Import as dinner
                        </button>
                      </div>
                    ) : (
                      <button
                        className="small-button"
                        disabled={!isOnline || busy === `import-${result.place_id}`}
                        type="button"
                        onClick={() => void addRemoteSpot(result)}
                      >
                        Import and add
                      </button>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        </div>

        <div className="two-column">
          <section className="panel">
            <div className="section-heading">
              <h2>Remove spot</h2>
              <p>Delete a candidate only from this trip and replan the remainder.</p>
            </div>
            <div className="stack">
              {removableCandidates.map((candidate) => (
                <article key={candidate.id} className="candidate-item">
                  <div className="candidate-title">{candidate.poi_name}</div>
                  <div className="timeline-meta">{candidate.primary_category}</div>
                  <button
                    className="small-button"
                    disabled={!isOnline || busy === `remove-${candidate.id}`}
                    type="button"
                    onClick={() => void removeCandidate(candidate.id)}
                  >
                    Remove from trip
                  </button>
                </article>
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Latest replan</h2>
              <p>Most recent response from the replan endpoint.</p>
            </div>
            {lastReplan ? (
              <div className="stack">
                <div className="candidate-item">
                  <div className="candidate-title">Feasible: {String(lastReplan.feasible)}</div>
                  <div className="timeline-meta">Solve time {lastReplan.solve_ms} ms</div>
                </div>
                {lastReplan.reason_codes.map((code) => (
                  <div key={code} className="reason-chip">
                    {humanizeReason(code)}
                  </div>
                ))}
              </div>
            ) : (
              <div className="candidate-item">
                <div className="timeline-meta">No replan has been run in this view yet.</div>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
