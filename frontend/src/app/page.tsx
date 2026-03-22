"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { TripSummary } from "@/lib/types";

export default function HomePage() {
  const [trips, setTrips] = useState<TripSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadTrips() {
      try {
        const response = await api<{ items: TripSummary[] }>("/api/trips");
        if (!cancelled) {
          setTrips(response.items);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "読み込みに失敗しました。");
        }
      }
    }
    void loadTrips();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page-shell">
      <div className="page-frame stack">
        <section className="hero-panel">
          <div className="section-heading">
            <span className="eyebrow">Generalized Travel Planner</span>
            <h1>単日旅行の候補集め、計画、実行をひとつに。</h1>
            <p>場所を集めて、ルールを作って、プレビューで比較し、当日は実行モードで再計画できます。</p>
          </div>
          <div className="button-row">
            <Link className="primary-button" href="/trips/new">
              新しい旅行を作成
            </Link>
            <Link className="secondary-button" href="/places">
              場所ライブラリ
            </Link>
          </div>
        </section>
        {error ? <p className="error-text">{error}</p> : null}
        <section className="panel">
          <div className="section-heading">
            <h2>最近の旅行</h2>
            <p>作業途中の旅行や、実行中の旅行に戻れます。</p>
          </div>
          <div className="stack">
            {trips.length === 0 ? (
              <div className="empty-card">まだ旅行がありません。</div>
            ) : (
              trips.map((trip) => (
                <article key={trip.id} className="candidate-card">
                  <div>
                    <div className="candidate-title">{trip.title}</div>
                    <div className="candidate-meta">
                      {trip.plan_date} / {trip.state}
                    </div>
                  </div>
                  <div className="button-row">
                    <Link className="small-button" href={`/trips/${trip.id}`}>
                      計画を開く
                    </Link>
                    <Link className="small-button" href={`/trips/${trip.id}/execute`}>
                      実行画面
                    </Link>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
