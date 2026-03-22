"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { CompareDrawer } from "@/components/planning/CompareDrawer";
import { CandidateBucket } from "@/components/planning/CandidateBucket";
import { ExplanationPanel } from "@/components/planning/ExplanationPanel";
import { PlanningMapCanvas } from "@/components/planning/PlanningMapCanvas";
import { RuleBuilder } from "@/components/planning/RuleBuilder";
import { SolveSummaryBar } from "@/components/planning/SolveSummaryBar";
import { TimelineEditor } from "@/components/planning/TimelineEditor";
import type { PlaceSummary, PreviewResponse, SolveAcceptedResponse, TripWorkspace } from "@/lib/types";

export default function TripWorkspacePage() {
  const params = useParams<{ id: string }>();
  const tripId = params.id;
  const [workspace, setWorkspace] = useState<TripWorkspace | null>(null);
  const [places, setPlaces] = useState<PlaceSummary[]>([]);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [orderedPlaceIds, setOrderedPlaceIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadWorkspace() {
    try {
      const [workspaceResponse, placesResponse] = await Promise.all([
        api<TripWorkspace>(`/api/trips/${tripId}`),
        api<{ items: PlaceSummary[] }>("/api/places"),
      ]);
      setWorkspace(workspaceResponse);
      setPlaces(placesResponse.items);
      setOrderedPlaceIds(
        workspaceResponse.latest_accepted_run?.selected_place_ids ?? workspaceResponse.candidates.map((candidate) => candidate.place_id),
      );
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "読み込みに失敗しました。");
    }
  }

  useEffect(() => {
    void loadWorkspace();
  }, [tripId]);

  useEffect(() => {
    if (!workspace || orderedPlaceIds.length === 0) {
      return;
    }
    const timer = window.setTimeout(async () => {
      try {
        const nextPreview = await api<PreviewResponse>(`/api/trips/${tripId}/preview`, {
          method: "POST",
          body: JSON.stringify({
            workspace_version: workspace.workspace_version,
            draft_order_edits: orderedPlaceIds,
          }),
        });
        setPreview(nextPreview);
      } catch (previewError) {
        setError(previewError instanceof Error ? previewError.message : "プレビューに失敗しました。");
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [orderedPlaceIds, tripId, workspace]);

  const candidatePlaceIds = useMemo(
    () => new Set(workspace?.candidates.map((candidate) => candidate.place_id) ?? []),
    [workspace],
  );
  const addablePlaces = places.filter((place) => !candidatePlaceIds.has(place.id) && !place.archived);

  async function addCandidate(placeId: number) {
    setBusy(true);
    try {
      await api(`/api/trips/${tripId}/candidates`, {
        method: "POST",
        body: JSON.stringify({ place_id: placeId, priority: "normal" }),
      });
      await loadWorkspace();
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "候補追加に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  async function createRule(payload: Record<string, unknown>) {
    setBusy(true);
    try {
      await api(`/api/trips/${tripId}/rules`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await loadWorkspace();
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "ルール追加に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  async function acceptCurrentPlan() {
    if (!workspace) {
      return;
    }
    setBusy(true);
    try {
      const response = await api<SolveAcceptedResponse>(`/api/trips/${tripId}/solve`, {
        method: "POST",
        body: JSON.stringify(
          preview
            ? { workspace_version: workspace.workspace_version, preview_id: preview.preview_id }
            : { workspace_version: workspace.workspace_version },
        ),
      });
      setPreview(null);
      await loadWorkspace();
      setOrderedPlaceIds(response.solve.selected_place_ids);
    } catch (solveError) {
      setError(solveError instanceof Error ? solveError.message : "計画の確定に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Planning Workspace</span>
            <h1>{workspace?.trip.title ?? "旅行ワークスペース"}</h1>
            <p>候補、ルール、プレビュー、比較、実行開始をひとつの画面で行います。</p>
          </div>
          <div className="button-row">
            <button className="primary-button" type="button" disabled={busy || !workspace} onClick={() => void acceptCurrentPlan()}>
              プレビューを確定
            </button>
            <Link className="secondary-button" href={`/trips/${tripId}/compare`}>
              比較ページ
            </Link>
            <Link className="secondary-button" href={`/trips/${tripId}/execute`}>
              実行ページ
            </Link>
          </div>
        </section>
        {error ? <p className="error-text">{error}</p> : null}
        {!workspace ? (
          <section className="panel">
            <div className="empty-card">読み込み中...</div>
          </section>
        ) : (
          <>
            <div className="workspace-grid">
              <div className="stack">
                <section className="panel">
                  <div className="section-heading">
                    <h2>場所追加</h2>
                    <p>ライブラリから旅行候補を追加します。</p>
                  </div>
                  <div className="stack">
                    {addablePlaces.slice(0, 6).map((place) => (
                      <article key={place.id} className="candidate-card">
                        <div>
                          <div className="candidate-title">{place.name}</div>
                          <div className="candidate-meta">{place.category ?? "未分類"}</div>
                        </div>
                        <button className="small-button" type="button" disabled={busy} onClick={() => void addCandidate(place.id)}>
                          追加
                        </button>
                      </article>
                    ))}
                  </div>
                </section>
                <CandidateBucket
                  candidates={workspace.candidates}
                  orderedPlaceIds={orderedPlaceIds}
                  onAdd={(placeId) => setOrderedPlaceIds((current) => [...current, placeId])}
                />
                <RuleBuilder candidates={workspace.candidates} rules={workspace.rules} onCreateRule={createRule} />
              </div>
              <div className="stack">
                <SolveSummaryBar solve={workspace.latest_accepted_run} label="確定版" />
                <SolveSummaryBar solve={preview?.solve ?? null} label="プレビュー" />
                <PlanningMapCanvas candidates={workspace.candidates} solve={preview?.solve ?? workspace.latest_accepted_run} />
                <TimelineEditor
                  candidates={workspace.candidates}
                  orderedPlaceIds={orderedPlaceIds}
                  solve={preview?.solve ?? workspace.latest_accepted_run}
                  onReorder={setOrderedPlaceIds}
                />
              </div>
              <div className="stack">
                <CompareDrawer accepted={workspace.latest_accepted_run} preview={preview?.solve ?? null} />
                <ExplanationPanel solve={preview?.solve ?? workspace.latest_accepted_run} rules={workspace.rules} />
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
