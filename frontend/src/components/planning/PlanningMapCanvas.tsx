"use client";

import type { Candidate, SolvePayload } from "@/lib/types";

type Point = {
  key: string;
  label: string;
  lat: number;
  lng: number;
  kind: "candidate" | "route";
};

function normalizePoints(points: Point[]) {
  if (points.length === 0) {
    return [];
  }
  const minLat = Math.min(...points.map((point) => point.lat));
  const maxLat = Math.max(...points.map((point) => point.lat));
  const minLng = Math.min(...points.map((point) => point.lng));
  const maxLng = Math.max(...points.map((point) => point.lng));
  const latRange = Math.max(0.01, maxLat - minLat);
  const lngRange = Math.max(0.01, maxLng - minLng);
  return points.map((point) => ({
    ...point,
    x: 20 + ((point.lng - minLng) / lngRange) * 360,
    y: 20 + ((maxLat - point.lat) / latRange) * 220,
  }));
}

export function PlanningMapCanvas({
  candidates,
  solve,
}: {
  candidates: Candidate[];
  solve: SolvePayload | null;
}) {
  const routePoints: Point[] =
    solve?.stops.map((stop) => ({
      key: `route-${stop.sequence_order}`,
      label: stop.label,
      lat: stop.lat,
      lng: stop.lng,
      kind: "route" as const,
    })) ?? [];
  const candidatePoints = candidates.map((candidate) => ({
    key: `candidate-${candidate.id}`,
    label: candidate.place.name,
    lat: candidate.place.lat,
    lng: candidate.place.lng,
    kind: "candidate" as const,
  }));
  const points = normalizePoints([...candidatePoints, ...routePoints]);
  const routeOnly = points.filter((point) => point.kind === "route");
  const candidateOnly = points.filter((point) => point.kind === "candidate");

  return (
    <section className="panel">
      <div className="section-heading">
        <h2>地図プレビュー</h2>
        <p>候補地と現在のルートを簡易マップで確認できます。</p>
      </div>
      <svg className="mini-map" viewBox="0 0 400 260" role="img" aria-label="Route preview map">
        <rect x="0" y="0" width="400" height="260" rx="20" fill="rgba(255,255,255,0.03)" />
        {routeOnly.length > 1 ? (
          <polyline
            fill="none"
            stroke="rgba(125, 226, 207, 0.9)"
            strokeWidth="4"
            points={routeOnly.map((point) => `${point.x},${point.y}`).join(" ")}
          />
        ) : null}
        {candidateOnly.map((point) => (
          <circle
            key={point.key}
            cx={point.x}
            cy={point.y}
            r="5"
            fill="rgba(255,255,255,0.35)"
          />
        ))}
        {routeOnly.map((point, index) => (
          <g key={point.key}>
            <circle cx={point.x} cy={point.y} r="8" fill="#7de2cf" />
            <text x={point.x + 10} y={point.y - 10} fill="#ecf6fb" fontSize="12">
              {index + 1}. {point.label}
            </text>
          </g>
        ))}
      </svg>
    </section>
  );
}
