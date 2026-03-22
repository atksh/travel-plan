"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  appleMapsHref,
  formatDuration,
  formatMinute,
  googleMapsHref,
  humanizeReason,
} from "@/lib/format";
import { api } from "@/lib/api";
import { loadPlanCache, savePlanCache, useOnlineStatus } from "@/lib/offline-cache";
import { buildRoutePoints } from "@/lib/stops";
import { RouteMap } from "@/components/RouteMap";
import type { CandidateOut, PlannedStopOut, PoiSummary, SolveResponse, TripDetailOut } from "@/lib/types";

function MapButtons({
  currentPoint,
  nextPoint,
}: {
  currentPoint: { lat: number; lng: number } | null | undefined;
  nextPoint: { lat: number; lng: number } | null | undefined;
}) {
  if (!currentPoint || !nextPoint) {
    return null;
  }
  return (
    <div className="button-row" style={{ marginTop: "0.75rem" }}>
      {[
        { label: "Apple Maps", hrefBuilder: appleMapsHref },
        { label: "Google Maps", hrefBuilder: googleMapsHref },
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

function PlanTimelineSection({
  trip,
  stops,
  poiById,
}: {
  trip: TripDetailOut;
  stops: PlannedStopOut[];
  poiById: Map<number, PoiSummary>;
}) {
  const points = buildRoutePoints(stops, trip, poiById);
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Timeline</h2>
        <p>Arrival, stay, and leg time for the current best route.</p>
      </div>
      <div className="timeline">
        {stops.map((stop, index) => (
          <article key={`${stop.sequence_order}-${stop.poi_id ?? stop.node_kind}`} className="timeline-stop">
            <div className="timeline-header">
              <div>
                <div className="timeline-title">{stop.poi_name || stop.node_kind}</div>
                <div className="timeline-meta">
                  {formatMinute(stop.arrival_min)} - {formatMinute(stop.departure_min)}
                </div>
              </div>
              <div className="status-pill">
                <span>{stop.node_kind}</span>
              </div>
            </div>
            <div className="timeline-meta">
              Stay {formatDuration(stop.stay_min)} | Drive from previous{" "}
              {formatDuration(stop.leg_from_prev_min)}
            </div>
            <MapButtons currentPoint={points[index]} nextPoint={points[index + 1]} />
          </article>
        ))}
      </div>
    </section>
  );
}

function ReasonListSection({ reasonCodes }: { reasonCodes: string[] }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Why this plan</h2>
        <p>
          {reasonCodes.length === 0
            ? "No warnings. The current route satisfies the active constraints."
            : "Machine-readable reason codes translated into short notes."}
        </p>
      </div>
      {reasonCodes.length > 0 ? (
        <div className="reason-list">
          {reasonCodes.map((code) => (
            <div key={code} className="reason-chip">
              {humanizeReason(code)}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function CandidateBoardSection({
  tripId,
  candidates,
  onChanged,
  readOnly,
}: {
  tripId: string;
  candidates: CandidateOut[];
  onChanged: () => Promise<void>;
  readOnly: boolean;
}) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function mutateCandidate(candidateId: number, init: RequestInit, fallback: string) {
    setBusyId(candidateId);
    setError(null);
    try {
      await api(`/api/trips/${tripId}/candidates/${candidateId}`, init);
      await onChanged();
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : fallback);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Trip candidates</h2>
        <p>
          {readOnly
            ? "Offline mode is read-only. Reconnect to edit candidates."
            : "Adjust must-visit and exclude flags without touching the master POI list."}
        </p>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <div className="stack">
        {candidates.map((candidate) => (
          <article key={candidate.id} className="candidate-item">
            <div className="candidate-header">
              <div>
                <div className="candidate-title">{candidate.poi_name}</div>
                <div className="timeline-meta">
                  {candidate.primary_category} | {candidate.source}
                </div>
              </div>
              <div className="status-pill">
                <span>{candidate.status}</span>
              </div>
            </div>
            <div className="button-row" style={{ marginTop: "0.85rem" }}>
              <button
                className={candidate.must_visit ? "tag-chip tag-chip-active" : "tag-chip"}
                disabled={readOnly || busyId === candidate.id}
                type="button"
                onClick={() =>
                  void mutateCandidate(
                    candidate.id,
                    {
                      method: "PATCH",
                      body: JSON.stringify({
                        must_visit: !candidate.must_visit,
                        excluded: false,
                      }),
                    },
                    "Action failed",
                  )
                }
              >
                {candidate.must_visit ? "Must visit" : "Make must"}
              </button>
              <button
                className={candidate.excluded ? "tag-chip tag-chip-active" : "tag-chip"}
                disabled={readOnly || busyId === candidate.id}
                type="button"
                onClick={() =>
                  void mutateCandidate(
                    candidate.id,
                    {
                      method: "PATCH",
                      body: JSON.stringify({
                        excluded: !candidate.excluded,
                        must_visit: false,
                      }),
                    },
                    "Action failed",
                  )
                }
              >
                {candidate.excluded ? "Excluded" : "Exclude"}
              </button>
              <button
                className="tag-chip"
                disabled={readOnly || busyId === candidate.id}
                type="button"
                onClick={() =>
                  void mutateCandidate(candidate.id, { method: "DELETE" }, "Delete failed")
                }
              >
                Remove
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export default function TripPage() {
  const params = useParams();
  const id = String(params.id);
  const [trip, setTrip] = useState<TripDetailOut | null>(null);
  const [pois, setPois] = useState<PoiSummary[]>([]);
  const [solve, setSolve] = useState<SolveResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [useTraffic, setUseTraffic] = useState(true);
  const isOnline = useOnlineStatus();

  const loadTripData = useCallback(async () => {
    try {
      const [tripData, poiData] = await Promise.all([
        api<TripDetailOut>(`/api/trips/${id}`),
        api<PoiSummary[]>("/api/pois"),
      ]);
      setTrip(tripData);
      setPois(poiData);
    } catch (loadError) {
      const cached = loadPlanCache(id);
      if (!cached) {
        throw loadError;
      }
      setTrip(cached.trip);
      setPois(cached.pois);
      setSolve(cached.solve);
      setErr("Showing the cached plan because the app is offline.");
    }
  }, [id]);

  const runSolve = useCallback(
    async (traffic: boolean) => {
      if (!isOnline) {
        const cached = loadPlanCache(id);
        if (cached) {
          setTrip(cached.trip);
          setPois(cached.pois);
          setSolve(cached.solve);
          setErr("Offline mode is read-only. Cached plan loaded.");
        }
        return;
      }
      setErr(null);
      setLoading(true);
      try {
        setSolve(
          await api<SolveResponse>(`/api/trips/${id}/solve`, {
            method: "POST",
            body: JSON.stringify({ use_traffic_matrix: traffic }),
          }),
        );
        await loadTripData();
      } catch (solveError) {
        setErr(solveError instanceof Error ? solveError.message : "Error");
      } finally {
        setLoading(false);
      }
    },
    [id, isOnline, loadTripData],
  );

  const refreshAfterCandidateChange = useCallback(async () => {
    await loadTripData();
    await runSolve(useTraffic);
  }, [loadTripData, runSolve, useTraffic]);

  useEffect(() => {
    if (!isOnline) {
      const cached = loadPlanCache(id);
      if (cached) {
        setTrip(cached.trip);
        setPois(cached.pois);
        setSolve(cached.solve);
        setErr("Offline mode is read-only. Cached plan loaded.");
      }
      return;
    }
    void (async () => {
      await loadTripData();
      await runSolve(useTraffic);
    })();
  }, [id, isOnline, loadTripData, runSolve, useTraffic]);

  useEffect(() => {
    if (trip && pois.length > 0) {
      savePlanCache(id, { trip, solve, pois });
    }
  }, [id, pois, solve, trip]);

  const poiById = useMemo(() => new Map(pois.map((poi) => [poi.id, poi])), [pois]);
  const plannedStops = solve?.planned_stops ?? trip?.latest_route ?? [];

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Plan view</span>
            <h1>Trip {id}</h1>
            <p>
              Solve the reduced graph, inspect the timeline, and adjust candidate
              flags before you leave.
            </p>
          </div>
          <div className="button-row">
            <button
              className="primary-button"
              disabled={loading || !isOnline}
              type="button"
              onClick={() => void runSolve(useTraffic)}
            >
              {loading ? "Solving…" : "Re-solve"}
            </button>
            <Link className="secondary-button" href={`/trips/${id}/active`}>
              Active trip
            </Link>
            <label className="checkbox-field">
              <input
                checked={useTraffic}
                type="checkbox"
                onChange={(event) => setUseTraffic(event.target.checked)}
              />
              <span>Use traffic-aware matrix</span>
            </label>
            {!isOnline ? <div className="offline-badge">Offline read-only mode</div> : null}
          </div>
          {solve ? (
            <div className="summary-row">
              <div className="summary-pill">
                <span>Feasible</span>
                <strong>{String(solve.feasible)}</strong>
              </div>
              <div className="summary-pill">
                <span>Objective</span>
                <strong>{solve.objective ?? "—"}</strong>
              </div>
              <div className="summary-pill">
                <span>Solve time</span>
                <strong>{solve.solve_ms} ms</strong>
              </div>
            </div>
          ) : null}
        </section>

        {err ? <p className="error-text">{err}</p> : null}

        {trip ? (
          <>
            <div className="split-panel">
              <PlanTimelineSection trip={trip} stops={plannedStops} poiById={poiById} />
              <div className="stack">
                <RouteMap trip={trip} stops={plannedStops} poiById={poiById} />
                <ReasonListSection reasonCodes={solve?.reason_codes ?? []} />
              </div>
            </div>

            <div className="split-panel">
              <CandidateBoardSection
                tripId={id}
                candidates={trip.candidates}
                onChanged={refreshAfterCandidateChange}
                readOnly={!isOnline}
              />
              <section className="panel">
                <div className="section-heading">
                  <h2>Solver notes</h2>
                  <p>The latest route and run summary stored on the backend.</p>
                </div>
                <div className="stack">
                  <div className="candidate-item">
                    <div className="candidate-title">State</div>
                    <div className="timeline-meta">{trip.state}</div>
                  </div>
                  <div className="candidate-item">
                    <div className="candidate-title">Weather mode</div>
                    <div className="timeline-meta">{trip.weather_mode}</div>
                  </div>
                  <div className="candidate-item">
                    <div className="candidate-title">Latest solver run</div>
                    <div className="timeline-meta">
                      {trip.latest_solver_run
                        ? `${trip.latest_solver_run.solve_ms} ms`
                        : "No run stored yet"}
                    </div>
                  </div>
                </div>
              </section>
            </div>
          </>
        ) : (
          <section className="panel">
            <p>Loading trip…</p>
          </section>
        )}
      </div>
    </main>
  );
}
