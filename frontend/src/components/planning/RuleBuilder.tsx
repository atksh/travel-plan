"use client";

import { useMemo, useState } from "react";
import type { Candidate, TripRule } from "@/lib/types";

export function RuleBuilder({
  candidates,
  rules,
  onCreateRule,
}: {
  candidates: Candidate[];
  rules: TripRule[];
  onCreateRule: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [mode, setMode] = useState("hard");
  const [ruleKind, setRuleKind] = useState("arrival_window");
  const [selectedPlaceId, setSelectedPlaceId] = useState<number | null>(candidates[0]?.place_id ?? null);
  const [weight, setWeight] = useState("5");
  const [minTime, setMinTime] = useState("10:00");
  const [maxTime, setMaxTime] = useState("12:00");
  const [tag, setTag] = useState("scenic");
  const [busy, setBusy] = useState(false);

  const selectablePlaces = useMemo(
    () => candidates.map((candidate) => ({ id: candidate.place_id, name: candidate.place.name })),
    [candidates],
  );

  async function handleSubmit() {
    if (ruleKind === "arrival_window" && selectedPlaceId === null) {
      return;
    }
    setBusy(true);
    try {
      if (ruleKind === "arrival_window") {
        await onCreateRule({
          rule_kind: "arrival_window",
          scope: "candidate",
          mode,
          weight: mode === "soft" ? Number(weight) : null,
          target: { kind: "place", value: selectedPlaceId, data: {} },
          operator: mode === "hard" ? "require_between" : "prefer",
          parameters: {
            arrive_after_min: Number(minTime.split(":")[0]) * 60 + Number(minTime.split(":")[1]),
            arrive_before_min: Number(maxTime.split(":")[0]) * 60 + Number(maxTime.split(":")[1]),
          },
          carry_forward_strategy: "stay_active",
          label: "到着時間ルール",
          description: "指定した時間帯に到着させる",
          created_by_surface: "ui",
        });
      } else {
        await onCreateRule({
          rule_kind: "preference_match",
          scope: "trip",
          mode: "soft",
          weight: Number(weight),
          target: { kind: "tag", value: tag, data: {} },
          operator: "prefer",
          parameters: {},
          carry_forward_strategy: "stay_active",
          label: "好みルール",
          description: "指定タグを優先する",
          created_by_surface: "ui",
        });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <h2>ルールビルダー</h2>
        <p>v1 では到着時間ルールとタグ優先ルールを作成できます。</p>
      </div>
      <div className="field-grid">
        <label className="field">
          <span>ルール種別</span>
          <select value={ruleKind} onChange={(event) => setRuleKind(event.target.value)}>
            <option value="arrival_window">到着時間</option>
            <option value="preference_match">タグ優先</option>
          </select>
        </label>
        <label className="field">
          <span>モード</span>
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="hard">Hard</option>
            <option value="soft">Soft</option>
          </select>
        </label>
        {ruleKind === "arrival_window" ? (
          <>
            <label className="field">
              <span>対象候補</span>
              <select
                value={selectedPlaceId ?? ""}
                onChange={(event) => setSelectedPlaceId(Number(event.target.value))}
              >
                {selectablePlaces.map((place) => (
                  <option key={place.id} value={place.id}>
                    {place.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>到着開始</span>
              <input type="time" value={minTime} onChange={(event) => setMinTime(event.target.value)} />
            </label>
            <label className="field">
              <span>到着終了</span>
              <input type="time" value={maxTime} onChange={(event) => setMaxTime(event.target.value)} />
            </label>
          </>
        ) : (
          <label className="field">
            <span>対象タグ</span>
            <input value={tag} onChange={(event) => setTag(event.target.value)} />
          </label>
        )}
        <label className="field">
          <span>重み</span>
          <input value={weight} onChange={(event) => setWeight(event.target.value)} />
        </label>
      </div>
      <div className="button-row">
        <button className="primary-button" type="button" disabled={busy || candidates.length === 0} onClick={() => void handleSubmit()}>
          ルールを追加
        </button>
        <span className="muted-text">現在 {rules.length} 件のルール</span>
      </div>
    </section>
  );
}
