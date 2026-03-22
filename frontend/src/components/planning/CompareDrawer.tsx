"use client";

import { summarizeSolveDiff } from "@/lib/format";
import type { SolvePayload } from "@/lib/types";

export function CompareDrawer({
  accepted,
  preview,
}: {
  accepted: SolvePayload | null;
  preview: SolvePayload | null;
}) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>比較</h2>
        <p>確定版と現在のプレビューの差分です。</p>
      </div>
      <div className="empty-card">{summarizeSolveDiff(accepted, preview)}</div>
      {accepted && preview ? (
        <div className="stack">
          <div className="summary-card">
            <span>確定版 stops</span>
            <strong>{accepted.selected_place_ids.length}</strong>
          </div>
          <div className="summary-card">
            <span>プレビュー stops</span>
            <strong>{preview.selected_place_ids.length}</strong>
          </div>
        </div>
      ) : null}
    </section>
  );
}
