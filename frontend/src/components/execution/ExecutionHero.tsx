"use client";

import { formatMinute } from "@/lib/format";
import type { ExecutionBootstrap } from "@/lib/types";

export function ExecutionHero({ bootstrap }: { bootstrap: ExecutionBootstrap }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>実行モード</h2>
        <p>現在地と次の行き先を確認します。</p>
      </div>
      <div className="summary-grid">
        <div className="summary-card">
          <span>現在</span>
          <strong>{bootstrap.current_stop?.label ?? "未設定"}</strong>
          <small>{bootstrap.current_stop ? formatMinute(bootstrap.current_stop.arrival_min) : "到着待ち"}</small>
        </div>
        <div className="summary-card">
          <span>次</span>
          <strong>{bootstrap.next_stop?.label ?? "なし"}</strong>
          <small>{bootstrap.next_stop ? formatMinute(bootstrap.next_stop.arrival_min) : "終端"}</small>
        </div>
        <div className="summary-card">
          <span>状態</span>
          <strong>{bootstrap.execution_session.status}</strong>
          <small>{bootstrap.replan_readiness.can_replan ? "再計画可能" : "再計画不可"}</small>
        </div>
      </div>
    </section>
  );
}
