"use client";

import type { SolvePayload, TripRule } from "@/lib/types";

export function ExplanationPanel({
  solve,
  rules,
}: {
  solve: SolvePayload | null;
  rules: TripRule[];
}) {
  const rulesById = new Map(rules.map((rule) => [rule.id, rule]));

  return (
    <section className="panel">
      <div className="section-heading">
        <h2>説明</h2>
        <p>ルール結果と未選択候補の理由を表示します。</p>
      </div>
      {!solve ? (
        <div className="empty-card">プレビュー後に説明が表示されます。</div>
      ) : (
        <div className="stack">
          {solve.rule_results.map((result) => (
            <article key={result.rule_id} className="candidate-card">
              <div className="candidate-title">
                {rulesById.get(result.rule_id)?.label ?? `Rule ${result.rule_id}`}
              </div>
              <div className="candidate-meta">
                {result.status} / score {result.score_impact}
              </div>
              <p className="body-copy">{result.explanation}</p>
            </article>
          ))}
          {solve.unselected_candidates.map((candidate) => (
            <article key={candidate.candidate_id} className="candidate-card">
              <div className="candidate-title">未選択候補 #{candidate.candidate_id}</div>
              <p className="body-copy">{candidate.explanation}</p>
            </article>
          ))}
          {solve.warnings.map((warning) => (
            <div key={warning} className="warning-card">
              {warning}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
