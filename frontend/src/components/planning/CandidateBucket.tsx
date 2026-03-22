"use client";

import type { Candidate } from "@/lib/types";

export function CandidateBucket({
  candidates,
  orderedPlaceIds,
  onAdd,
}: {
  candidates: Candidate[];
  orderedPlaceIds: number[];
  onAdd: (placeId: number) => void;
}) {
  const bucketItems = candidates.filter(
    (candidate) => !orderedPlaceIds.includes(candidate.place_id),
  );

  return (
    <section className="panel">
      <div className="section-heading">
        <h2>候補バケット</h2>
        <p>まだタイムラインに入っていない候補です。</p>
      </div>
      <div className="stack">
        {bucketItems.length === 0 ? (
          <div className="empty-card">未配置の候補はありません。</div>
        ) : (
          bucketItems.map((candidate) => (
            <article key={candidate.id} className="candidate-card">
              <div>
                <div className="candidate-title">{candidate.place.name}</div>
                <div className="candidate-meta">
                  {candidate.place.category ?? "未分類"} / {candidate.priority}
                </div>
              </div>
              <button className="small-button" type="button" onClick={() => onAdd(candidate.place_id)}>
                タイムラインへ追加
              </button>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
