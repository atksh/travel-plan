"use client";

import { formatDistance, formatDuration, formatMinute } from "@/lib/format";
import type { SolvePayload } from "@/lib/types";

export function SolveSummaryBar({
  solve,
  label,
}: {
  solve: SolvePayload | null;
  label: string;
}) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>{label}</h2>
        <p>現在の計画状態の概要です。</p>
      </div>
      {solve ? (
        <div className="summary-grid">
          <div className="summary-card">
            <span>実行可能</span>
            <strong>{solve.summary.feasible ? "はい" : "いいえ"}</strong>
          </div>
          <div className="summary-card">
            <span>運転時間</span>
            <strong>{formatDuration(solve.summary.total_drive_minutes)}</strong>
          </div>
          <div className="summary-card">
            <span>滞在時間</span>
            <strong>{formatDuration(solve.summary.total_stay_minutes)}</strong>
          </div>
          <div className="summary-card">
            <span>距離</span>
            <strong>{formatDistance(solve.summary.total_distance_meters)}</strong>
          </div>
          <div className="summary-card">
            <span>開始</span>
            <strong>{formatMinute(solve.summary.start_time_min)}</strong>
          </div>
          <div className="summary-card">
            <span>終了</span>
            <strong>{formatMinute(solve.summary.end_time_min)}</strong>
          </div>
        </div>
      ) : (
        <div className="empty-card">まだ計画がありません。</div>
      )}
    </section>
  );
}
