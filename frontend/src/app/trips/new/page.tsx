"use client";

import { useRouter } from "next/navigation";
import {
  useEffect,
  useState,
  type Dispatch,
  type FormEvent,
  type SetStateAction,
} from "react";
import {
  groupCategoryLabel,
  localDateInputValue,
  timeInputValue,
} from "@/lib/format";
import { api } from "@/lib/api";
import {
  buildTripCreatePayload,
  resolveDefaultMustVisitPoiIds,
  type TripCreateFormState,
} from "@/lib/trip-create";
import type { PoiSummary, TripDetailOut } from "@/lib/types";

const DEFAULT_ORIGIN = { label: "Tokyo Iriya", lat: 35.727, lng: 139.791 };
const DEFAULT_DESTINATION = {
  label: "Tokyo Iriya return",
  lat: 35.727,
  lng: 139.791,
};
const LUNCH_TAGS = ["seafood", "cafe", "scenic", "quick"];
const DINNER_TAGS = ["seafood", "sushi", "romantic", "local"];

function toggleInList(list: string[], value: string): string[] {
  return list.includes(value)
    ? list.filter((item) => item !== value)
    : [...list, value];
}

function togglePoiId(list: number[], poiId: number): number[] {
  return list.includes(poiId)
    ? list.filter((id) => id !== poiId)
    : [...list, poiId];
}

function buildInitialFormState(): TripCreateFormState {
  return {
    planDate: "",
    originLabel: DEFAULT_ORIGIN.label,
    originLat: String(DEFAULT_ORIGIN.lat),
    originLng: String(DEFAULT_ORIGIN.lng),
    destLabel: DEFAULT_DESTINATION.label,
    destLat: String(DEFAULT_DESTINATION.lat),
    destLng: String(DEFAULT_DESTINATION.lng),
    departureStart: timeInputValue(8 * 60),
    departureEnd: timeInputValue(9 * 60),
    returnDeadline: timeInputValue((25 * 60) % (24 * 60)),
    weatherMode: "normal",
    drivingPenaltyWeight: 0.05,
    maxContinuousDriveMinutes: 120,
    mustHaveCafe: false,
    budgetBand: "moderate",
    paceStyle: "balanced",
  };
}

function groupPois(pois: PoiSummary[]): Array<[string, PoiSummary[]]> {
  const grouped = new Map<string, PoiSummary[]>();
  for (const poi of pois) {
    grouped.set(poi.primary_category, [
      ...(grouped.get(poi.primary_category) ?? []),
      poi,
    ]);
  }
  return Array.from(grouped.entries()).sort((a, b) => a[0].localeCompare(b[0]));
}

type TagGroup = {
  title: string;
  tags: string[];
  selected: string[];
  setSelected: Dispatch<SetStateAction<string[]>>;
};

type PoiPickerProps = {
  title: string;
  caption: string;
  pois: PoiSummary[];
  selectedIds: number[];
  onToggle: (poiId: number) => void;
};

function PoiPicker({
  title,
  caption,
  pois,
  selectedIds,
  onToggle,
}: PoiPickerProps) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>{title}</h2>
        <p>{caption}</p>
      </div>
      <div className="picker-groups">
        {groupPois(pois).map(([category, items]) => (
          <div key={category} className="picker-group">
            <div className="picker-group-title">{groupCategoryLabel(category)}</div>
            <div className="picker-grid">
              {items.map((poi) => {
                const checked = selectedIds.includes(poi.id);
                return (
                  <label
                    key={poi.id}
                    className={checked ? "picker-card picker-card-active" : "picker-card"}
                  >
                    <input
                      checked={checked}
                      type="checkbox"
                      onChange={() => onToggle(poi.id)}
                    />
                    <span className="picker-card-title">{poi.name}</span>
                    <span className="picker-card-subtitle">
                      {groupCategoryLabel(poi.primary_category)}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function NewTripPage() {
  const router = useRouter();
  const [pois, setPois] = useState<PoiSummary[]>([]);
  const [mustVisitIds, setMustVisitIds] = useState<number[]>([]);
  const [excludeIds, setExcludeIds] = useState<number[]>([]);
  const [preferredLunchTags, setPreferredLunchTags] = useState<string[]>(["seafood"]);
  const [preferredDinnerTags, setPreferredDinnerTags] = useState<string[]>(["seafood"]);
  const [loading, setLoading] = useState(false);
  const [loadingPois, setLoadingPois] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<TripCreateFormState>(buildInitialFormState);
  const tagGroups: TagGroup[] = [
    {
      title: "Lunch tags",
      tags: LUNCH_TAGS,
      selected: preferredLunchTags,
      setSelected: setPreferredLunchTags,
    },
    {
      title: "Dinner tags",
      tags: DINNER_TAGS,
      selected: preferredDinnerTags,
      setSelected: setPreferredDinnerTags,
    },
  ];

  useEffect(() => {
    let cancelled = false;
    async function loadPois() {
      setLoadingPois(true);
      try {
        const data = await api<PoiSummary[]>("/api/pois");
        if (cancelled) {
          return;
        }
        setPois(data);
        setMustVisitIds(resolveDefaultMustVisitPoiIds(data));
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load POIs");
        }
      } finally {
        if (!cancelled) {
          setLoadingPois(false);
        }
      }
    }
    void loadPois();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setForm((current) =>
      current.planDate ? current : { ...current, planDate: localDateInputValue() },
    );
  }, []);

  function updateField<K extends keyof TripCreateFormState>(
    key: K,
    value: TripCreateFormState[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function applyPoint(
    prefix: "origin" | "dest",
    point: { label: string; lat: number; lng: number },
  ) {
    setForm((current) => ({
      ...current,
      [`${prefix}Label`]: point.label,
      [`${prefix}Lat`]: String(point.lat),
      [`${prefix}Lng`]: String(point.lng),
    }));
  }

  function toggleSelection(
    poiId: number,
    setSelected: Dispatch<SetStateAction<number[]>>,
    setCleared: Dispatch<SetStateAction<number[]>>,
  ) {
    setSelected((current) => togglePoiId(current, poiId));
    setCleared((current) => current.filter((id) => id !== poiId));
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setError("Geolocation is not available on this device.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        applyPoint("origin", {
          label: "Current location",
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        }),
      () => setError("Could not read the current location."),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const trip = await api<TripDetailOut>("/api/trips", {
        method: "POST",
        body: JSON.stringify(
          buildTripCreatePayload(
            form,
            mustVisitIds,
            excludeIds,
            preferredLunchTags,
            preferredDinnerTags,
          ),
        ),
      });
      router.push(`/trips/${trip.id}`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to create trip");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="page-frame">
        <form className="setup-grid" onSubmit={onSubmit}>
          <section className="hero-panel">
            <div className="section-heading">
              <span className="eyebrow">Trip setup</span>
              <h1>Build a date plan that can survive the day itself.</h1>
              <p>
                Set the trip frame, choose must-go and no-go spots, and bias the
                solver toward the pace you want on iPhone.
              </p>
            </div>
            <div className="summary-row">
              <div className="summary-pill">
                <span>Must visit</span>
                <strong>{mustVisitIds.length}</strong>
              </div>
              <div className="summary-pill">
                <span>Excluded</span>
                <strong>{excludeIds.length}</strong>
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Trip frame</h2>
              <p>Core timing and endpoints used by the planner.</p>
            </div>
            <div className="field-grid">
              <label className="field">
                <span>Date</span>
                <input
                  type="date"
                  value={form.planDate}
                  onChange={(event) => updateField("planDate", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Weather mode</span>
                <select
                  value={form.weatherMode}
                  onChange={(event) => updateField("weatherMode", event.target.value)}
                >
                  <option value="normal">Normal</option>
                  <option value="rain">Rain</option>
                </select>
              </label>
              <label className="field">
                <span>Departure window start</span>
                <input
                  type="time"
                  value={form.departureStart}
                  onChange={(event) => updateField("departureStart", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Departure window end</span>
                <input
                  type="time"
                  value={form.departureEnd}
                  onChange={(event) => updateField("departureEnd", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Return deadline</span>
                <input
                  type="time"
                  value={form.returnDeadline}
                  onChange={(event) => updateField("returnDeadline", event.target.value)}
                />
              </label>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Origin</h2>
              <p>Use a known default or overwrite with your actual start point.</p>
            </div>
            <div className="button-row">
              <button
                className="secondary-button"
                type="button"
                onClick={() => applyPoint("origin", DEFAULT_ORIGIN)}
              >
                Use Tokyo Iriya
              </button>
              <button className="secondary-button" type="button" onClick={useCurrentLocation}>
                Use current location
              </button>
            </div>
            <div className="field-grid">
              <label className="field">
                <span>Origin label</span>
                <input
                  value={form.originLabel}
                  onChange={(event) => updateField("originLabel", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Origin latitude</span>
                <input
                  value={form.originLat}
                  onChange={(event) => updateField("originLat", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Origin longitude</span>
                <input
                  value={form.originLng}
                  onChange={(event) => updateField("originLng", event.target.value)}
                />
              </label>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Destination</h2>
              <p>Usually the return point, but you can finish elsewhere.</p>
            </div>
            <div className="button-row">
              <button
                className="secondary-button"
                type="button"
                onClick={() => applyPoint("dest", DEFAULT_DESTINATION)}
              >
                Use Tokyo return
              </button>
            </div>
            <div className="field-grid">
              <label className="field">
                <span>Destination label</span>
                <input
                  value={form.destLabel}
                  onChange={(event) => updateField("destLabel", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Destination latitude</span>
                <input
                  value={form.destLat}
                  onChange={(event) => updateField("destLat", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Destination longitude</span>
                <input
                  value={form.destLng}
                  onChange={(event) => updateField("destLng", event.target.value)}
                />
              </label>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Preferences</h2>
              <p>These values shape the comfort-vs-distance tradeoff.</p>
            </div>
            <div className="field-grid">
              <label className="field">
                <span>Driving penalty weight</span>
                <input
                  max="0.2"
                  min="0.01"
                  step="0.01"
                  type="range"
                  value={form.drivingPenaltyWeight}
                  onChange={(event) =>
                    updateField("drivingPenaltyWeight", Number(event.target.value))
                  }
                />
                <small>{form.drivingPenaltyWeight.toFixed(2)}</small>
              </label>
              <label className="field">
                <span>Max continuous drive (min)</span>
                <input
                  max="240"
                  min="45"
                  step="15"
                  type="range"
                  value={form.maxContinuousDriveMinutes}
                  onChange={(event) =>
                    updateField("maxContinuousDriveMinutes", Number(event.target.value))
                  }
                />
                <small>{form.maxContinuousDriveMinutes} min</small>
              </label>
              <label className="field">
                <span>Pace style</span>
                <select
                  value={form.paceStyle}
                  onChange={(event) => updateField("paceStyle", event.target.value)}
                >
                  <option value="relaxed">Relaxed</option>
                  <option value="balanced">Balanced</option>
                  <option value="packed">Packed</option>
                </select>
              </label>
              <label className="field">
                <span>Budget band</span>
                <select
                  value={form.budgetBand}
                  onChange={(event) => updateField("budgetBand", event.target.value)}
                >
                  <option value="casual">Casual</option>
                  <option value="moderate">Moderate</option>
                  <option value="premium">Premium</option>
                </select>
              </label>
              <label className="field checkbox-field">
                <input
                  checked={form.mustHaveCafe}
                  type="checkbox"
                  onChange={(event) => updateField("mustHaveCafe", event.target.checked)}
                />
                <span>Must include a cafe stop</span>
              </label>
            </div>
            <div className="tag-zone">
              {tagGroups.map(({ title, tags, selected, setSelected }) => (
                <div key={title} className="tag-group">
                  <span className="tag-group-title">{title}</span>
                  <div className="tag-row">
                    {tags.map((tag) => (
                      <button
                        key={tag}
                        className={
                          selected.includes(tag)
                            ? "tag-chip tag-chip-active"
                            : "tag-chip"
                        }
                        type="button"
                        onClick={() => setSelected((current) => toggleInList(current, tag))}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {loadingPois ? (
            <section className="panel">
              <p>Loading POIs…</p>
            </section>
          ) : (
            <>
              <PoiPicker
                title="Must visit"
                caption="These spots are locked as hard requirements."
                pois={pois}
                selectedIds={mustVisitIds}
                onToggle={(poiId) => toggleSelection(poiId, setMustVisitIds, setExcludeIds)}
              />
              <PoiPicker
                title="Exclude from this trip"
                caption="Use this when you want to keep a spot in the master POI list but not on this date."
                pois={pois}
                selectedIds={excludeIds}
                onToggle={(poiId) => toggleSelection(poiId, setExcludeIds, setMustVisitIds)}
              />
            </>
          )}

          <section className="panel submit-panel">
            {error ? <p className="error-text">{error}</p> : null}
            <button className="primary-button" disabled={loading} type="submit">
              {loading ? "Creating trip…" : "Create trip and open plan"}
            </button>
          </section>
        </form>
      </div>
    </main>
  );
}
