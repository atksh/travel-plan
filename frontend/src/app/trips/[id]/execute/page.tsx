"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ExecutionActionBar } from "@/components/execution/ExecutionActionBar";
import { ExecutionHero } from "@/components/execution/ExecutionHero";
import { PlanningMapCanvas } from "@/components/planning/PlanningMapCanvas";
import type {
  ExecutionBootstrap,
  ExecutionStartResponse,
  PreviewResponse,
  ReplanAcceptedResponse,
} from "@/lib/types";

export default function ExecutePage() {
  const params = useParams<{ id: string }>();
  const tripId = params.id;
  const [bootstrap, setBootstrap] = useState<ExecutionBootstrap | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function loadBootstrap() {
    try {
      const response = await api<ExecutionBootstrap>(`/api/trips/${tripId}/execution/bootstrap`);
      setBootstrap(response);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "実行情報の取得に失敗しました。");
    }
  }

  useEffect(() => {
    void loadBootstrap();
  }, [tripId]);

  async function startExecution() {
    setBusy(true);
    try {
      await api<ExecutionStartResponse>(`/api/trips/${tripId}/execution/start`, {
        method: "POST",
      });
      await loadBootstrap();
      setMessage("実行を開始しました。");
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : "実行開始に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  async function sendEvent(eventType: string) {
    if (!bootstrap?.current_stop?.place_id) {
      return;
    }
    setBusy(true);
    try {
      await api(`/api/trips/${tripId}/execution/events`, {
        method: "POST",
        body: JSON.stringify({
          event_type: eventType,
          payload: { place_id: bootstrap.current_stop.place_id },
        }),
      });
      await loadBootstrap();
      setMessage(`${eventType} を記録しました。`);
    } catch (eventError) {
      setError(eventError instanceof Error ? eventError.message : "イベント記録に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  async function previewReplan() {
    if (!bootstrap) {
      return;
    }
    setBusy(true);
    try {
      const response = await api<PreviewResponse>(`/api/trips/${tripId}/execution/replan-preview`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setPreview(response);
      setMessage("再計画プレビューを更新しました。");
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : "再計画プレビューに失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  async function acceptReplan() {
    if (!bootstrap || !preview) {
      return;
    }
    setBusy(true);
    try {
      await api<ReplanAcceptedResponse>(`/api/trips/${tripId}/execution/replan`, {
        method: "POST",
        body: JSON.stringify({
          preview_id: preview.preview_id,
          workspace_version: preview.workspace_version,
        }),
      });
      setPreview(null);
      await loadBootstrap();
      setMessage("再計画を採用しました。");
    } catch (acceptError) {
      setError(acceptError instanceof Error ? acceptError.message : "再計画の採用に失敗しました。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Execution</span>
            <h1>実行モード</h1>
            <p>当日の移動状況を記録し、必要なら残り行程を再計画します。</p>
          </div>
          <div className="button-row">
            <button className="primary-button" type="button" disabled={busy} onClick={() => void startExecution()}>
              実行開始
            </button>
            <Link className="secondary-button" href={`/trips/${tripId}`}>
              ワークスペースへ戻る
            </Link>
          </div>
        </section>
        {message ? <p className="success-text">{message}</p> : null}
        {error ? <p className="error-text">{error}</p> : null}
        {bootstrap ? (
          <>
            <ExecutionHero bootstrap={bootstrap} />
            <ExecutionActionBar
              disabled={busy || !bootstrap.current_stop}
              onArrive={() => void sendEvent("arrived")}
              onDepart={() => void sendEvent("departed")}
              onSkip={() => void sendEvent("skipped")}
              onPreviewReplan={() => void previewReplan()}
              onAcceptReplan={() => void acceptReplan()}
              hasPreview={preview !== null}
            />
            <PlanningMapCanvas candidates={[]} solve={preview?.solve ?? bootstrap.active_solve} />
          </>
        ) : (
          <section className="panel">
            <div className="empty-card">実行情報を読み込み中です。</div>
          </section>
        )}
      </div>
    </main>
  );
}
