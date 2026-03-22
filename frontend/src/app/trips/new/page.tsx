"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { dateInputValue, timeInputValue } from "@/lib/format";
import { buildTripCreatePayload, type TripCreateFormState } from "@/lib/trip-create";
import type { TripWorkspace } from "@/lib/types";

function buildInitialState(): TripCreateFormState {
  return {
    title: "新しい日帰り旅行",
    planDate: dateInputValue(),
    timezone: "Asia/Tokyo",
    originLabel: "出発地",
    originLat: "35.72",
    originLng: "139.79",
    destinationLabel: "到着地",
    destinationLat: "35.45",
    destinationLng: "139.92",
    departureStart: timeInputValue(8 * 60),
    departureEnd: timeInputValue(9 * 60),
    endMinute: timeInputValue(21 * 60),
    endKind: "arrive_by",
    weather: "",
  };
}

export default function NewTripPage() {
  const router = useRouter();
  const [form, setForm] = useState<TripCreateFormState>(buildInitialState);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const response = await api<TripWorkspace>("/api/trips", {
        method: "POST",
        body: JSON.stringify(buildTripCreatePayload(form)),
      });
      router.push(`/trips/${response.trip.id}`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "旅行の作成に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Trip Frame</span>
            <h1>旅行フレームを作成</h1>
            <p>まずは日付、出発地、到着地、時間帯だけを決めます。候補地は次の画面で追加します。</p>
          </div>
        </section>
        {error ? <p className="error-text">{error}</p> : null}
        <section className="panel">
          <div className="field-grid">
            <label className="field">
              <span>タイトル</span>
              <input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
            </label>
            <label className="field">
              <span>日付</span>
              <input type="date" value={form.planDate} onChange={(event) => setForm((current) => ({ ...current, planDate: event.target.value }))} />
            </label>
            <label className="field">
              <span>タイムゾーン</span>
              <input value={form.timezone} onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))} />
            </label>
            <label className="field">
              <span>天候コンテキスト</span>
              <input value={form.weather} onChange={(event) => setForm((current) => ({ ...current, weather: event.target.value }))} placeholder="rain など" />
            </label>
            <label className="field">
              <span>出発ラベル</span>
              <input value={form.originLabel} onChange={(event) => setForm((current) => ({ ...current, originLabel: event.target.value }))} />
            </label>
            <label className="field">
              <span>出発緯度</span>
              <input value={form.originLat} onChange={(event) => setForm((current) => ({ ...current, originLat: event.target.value }))} />
            </label>
            <label className="field">
              <span>出発経度</span>
              <input value={form.originLng} onChange={(event) => setForm((current) => ({ ...current, originLng: event.target.value }))} />
            </label>
            <label className="field">
              <span>到着ラベル</span>
              <input value={form.destinationLabel} onChange={(event) => setForm((current) => ({ ...current, destinationLabel: event.target.value }))} />
            </label>
            <label className="field">
              <span>到着緯度</span>
              <input value={form.destinationLat} onChange={(event) => setForm((current) => ({ ...current, destinationLat: event.target.value }))} />
            </label>
            <label className="field">
              <span>到着経度</span>
              <input value={form.destinationLng} onChange={(event) => setForm((current) => ({ ...current, destinationLng: event.target.value }))} />
            </label>
            <label className="field">
              <span>出発開始</span>
              <input type="time" value={form.departureStart} onChange={(event) => setForm((current) => ({ ...current, departureStart: event.target.value }))} />
            </label>
            <label className="field">
              <span>出発終了</span>
              <input type="time" value={form.departureEnd} onChange={(event) => setForm((current) => ({ ...current, departureEnd: event.target.value }))} />
            </label>
            <label className="field">
              <span>終了制約</span>
              <select value={form.endKind} onChange={(event) => setForm((current) => ({ ...current, endKind: event.target.value }))}>
                <option value="arrive_by">arrive_by</option>
                <option value="end_of_day">end_of_day</option>
              </select>
            </label>
            <label className="field">
              <span>終了時刻</span>
              <input type="time" value={form.endMinute} onChange={(event) => setForm((current) => ({ ...current, endMinute: event.target.value }))} />
            </label>
          </div>
          <button className="primary-button" type="button" disabled={busy} onClick={() => void submit()}>
            {busy ? "作成中..." : "旅行ワークスペースを作成"}
          </button>
        </section>
      </div>
    </main>
  );
}
