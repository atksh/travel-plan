"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { summarizeSolveDiff } from "@/lib/format";
import type { SolvePayload, SolveRunListItem, TripWorkspace } from "@/lib/types";

export default function ComparePage() {
  const params = useParams<{ id: string }>();
  const tripId = params.id;
  const [workspace, setWorkspace] = useState<TripWorkspace | null>(null);
  const [runs, setRuns] = useState<SolveRunListItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedRun, setSelectedRun] = useState<SolvePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [workspaceResponse, runResponse] = await Promise.all([
          api<TripWorkspace>(`/api/trips/${tripId}`),
          api<{ items: SolveRunListItem[] }>(`/api/trips/${tripId}/solve-runs`),
        ]);
        if (!cancelled) {
          setWorkspace(workspaceResponse);
          setRuns(runResponse.items);
          setSelectedRunId(runResponse.items[0]?.solve_run_id ?? null);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "比較情報の取得に失敗しました。");
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [tripId]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    let cancelled = false;
    async function loadRun() {
      try {
        const response = await api<SolvePayload>(`/api/trips/${tripId}/solve-runs/${selectedRunId}`);
        if (!cancelled) {
          setSelectedRun(response);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "比較対象の取得に失敗しました。");
        }
      }
    }
    void loadRun();
    return () => {
      cancelled = true;
    };
  }, [selectedRunId, tripId]);

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Compare</span>
            <h1>比較ビュー</h1>
            <p>確定版と過去の solve run を比較できます。</p>
          </div>
          <div className="button-row">
            <Link className="secondary-button" href={`/trips/${tripId}`}>
              ワークスペースへ戻る
            </Link>
          </div>
        </section>
        {error ? <p className="error-text">{error}</p> : null}
        <section className="panel">
          <div className="field">
            <span>比較対象 run</span>
            <select value={selectedRunId ?? ""} onChange={(event) => setSelectedRunId(Number(event.target.value))}>
              {runs.map((run) => (
                <option key={run.solve_run_id} value={run.solve_run_id}>
                  {run.run_kind} / {run.accepted_at}
                </option>
              ))}
            </select>
          </div>
        </section>
        <section className="panel">
          <div className="section-heading">
            <h2>差分サマリー</h2>
          </div>
          <div className="empty-card">
            {summarizeSolveDiff(workspace?.latest_accepted_run ?? null, selectedRun)}
          </div>
        </section>
        <div className="two-column">
          <section className="panel">
            <div className="section-heading">
              <h2>確定版</h2>
            </div>
            <div className="stack">
              {(workspace?.latest_accepted_run?.stops ?? []).map((stop) => (
                <div key={`accepted-${stop.sequence_order}`} className="candidate-card">
                  {stop.label}
                </div>
              ))}
            </div>
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>比較対象</h2>
            </div>
            <div className="stack">
              {(selectedRun?.stops ?? []).map((stop) => (
                <div key={`selected-${stop.sequence_order}`} className="candidate-card">
                  {stop.label}
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
