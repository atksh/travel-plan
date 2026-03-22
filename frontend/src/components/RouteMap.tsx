"use client";

import { useEffect, useMemo } from "react";
import {
  APIProvider,
  AdvancedMarker,
  Map,
  useMap,
} from "@vis.gl/react-google-maps";
import { buildRoutePoints } from "@/lib/stops";
import type { PoiSummary, TripDetailOut, PlannedStopOut } from "@/lib/types";

type GoogleWindow = Window & {
  google?: {
    maps: {
      Polyline: new (options: Record<string, unknown>) => {
        setMap: (map: unknown | null) => void;
      };
    };
  };
};

type RouteMapProps = {
  trip: TripDetailOut;
  stops: PlannedStopOut[];
  poiById: Map<number, PoiSummary>;
};

function RoutePolyline({
  points,
}: {
  points: Array<{ lat: number; lng: number }>;
}) {
  const map = useMap();

  useEffect(() => {
    const googleWindow = window as GoogleWindow;
    if (!map || !googleWindow.google || points.length < 2) {
      return undefined;
    }
    const polyline = new googleWindow.google.maps.Polyline({
      path: points,
      strokeColor: "#7de2cf",
      strokeOpacity: 0.95,
      strokeWeight: 4,
    });
    polyline.setMap(map);
    return () => {
      polyline.setMap(null);
    };
  }, [map, points]);

  return null;
}

export function RouteMap({ trip, stops, poiById }: RouteMapProps) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  const points = buildRoutePoints(stops, trip, poiById);
  const center = useMemo(() => {
    return (
      points[0] || {
        lat: trip.origin_lat,
        lng: trip.origin_lng,
        label: trip.origin_label,
      }
    );
  }, [points, trip]);

  if (points.length === 0) {
    return (
      <section className="map-panel">
        <div className="section-heading">
          <h2>Map</h2>
          <p>No route is available yet.</p>
        </div>
      </section>
    );
  }

  if (!apiKey) {
    return (
      <section className="map-panel">
        <div className="section-heading">
          <h2>Map</h2>
          <p>
            Add <code>NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> to render the live
            Google map. The route points are ready.
          </p>
        </div>
        <div className="stack">
          {points.map((point) => (
            <div key={`${point.label}-${point.lat}-${point.lng}`} className="candidate-item">
              <div className="candidate-title">{point.label}</div>
              <div className="timeline-meta">
                {point.lat.toFixed(4)}, {point.lng.toFixed(4)}
              </div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="map-panel">
      <div className="section-heading">
        <h2>Map</h2>
        <p>Live Google Maps view of the current route order.</p>
      </div>
      <div style={{ height: "420px", borderRadius: "18px", overflow: "hidden" }}>
        <APIProvider apiKey={apiKey}>
          <Map
            defaultCenter={{ lat: center.lat, lng: center.lng }}
            defaultZoom={9}
            gestureHandling="greedy"
            mapId="bosodrive-plan-map"
          >
            {points.map((point, index) => (
              <AdvancedMarker
                key={`${point.label}-${point.lat}-${point.lng}`}
                position={{ lat: point.lat, lng: point.lng }}
              >
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: 999,
                    display: "grid",
                    placeItems: "center",
                    background: "rgba(10, 29, 42, 0.92)",
                    color: "#ecf6fb",
                    border: "1px solid rgba(125, 226, 207, 0.65)",
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  {index + 1}
                </div>
              </AdvancedMarker>
            ))}
            <RoutePolyline points={points} />
          </Map>
        </APIProvider>
      </div>
    </section>
  );
}
