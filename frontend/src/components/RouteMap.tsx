"use client";

import { useEffect, useMemo } from "react";
import {
  APIProvider,
  AdvancedMarker,
  Map,
  useMap,
  useMapsLibrary,
} from "@vis.gl/react-google-maps";
import { buildRoutePoints } from "@/lib/stops";
import { GOOGLE_MAPS_API_KEY } from "@/lib/runtime-config";
import type { RouteLegOut, PlannedStopOut } from "@/lib/types";

type GoogleWindow = Window & {
  google?: {
    maps: {
      Polyline: new (options: Record<string, unknown>) => {
        setMap: (map: unknown | null) => void;
      };
      geometry?: {
        encoding?: {
          decodePath: (encodedPath: string) => unknown[];
        };
      };
    };
  };
};

type RouteMapProps = {
  stops: PlannedStopOut[];
  routeLegs: RouteLegOut[];
};

function RoutePolyline({
  points,
  stops,
  routeLegs,
}: {
  points: Array<{ lat: number; lng: number }>;
  stops: PlannedStopOut[];
  routeLegs: RouteLegOut[];
}) {
  const map = useMap();
  const geometryLibrary = useMapsLibrary("geometry");

  useEffect(() => {
    const googleWindow = window as GoogleWindow;
    if (!map || !googleWindow.google || points.length < 2) {
      return undefined;
    }
    const decodedPath: unknown[] = [];
    const decodePath =
      geometryLibrary && googleWindow.google.maps.geometry?.encoding?.decodePath
        ? googleWindow.google.maps.geometry.encoding.decodePath
        : null;

    for (const routeLeg of routeLegs) {
      if (decodePath) {
        decodedPath.push(...decodePath(routeLeg.encoded_polyline));
        continue;
      }
    }

    const polyline = new googleWindow.google.maps.Polyline({
      path: decodedPath.length >= 2 ? decodedPath : points,
      strokeColor: "#7de2cf",
      strokeOpacity: 0.95,
      strokeWeight: 4,
    });
    polyline.setMap(map);
    return () => {
      polyline.setMap(null);
    };
  }, [geometryLibrary, map, points, routeLegs, stops]);

  return null;
}

export function RouteMap({ stops, routeLegs }: RouteMapProps) {
  const points = buildRoutePoints(stops);
  const center = useMemo(() => {
    return points[0];
  }, [points]);

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

  return (
    <section className="map-panel">
      <div className="section-heading">
        <h2>Map</h2>
        <p>Live Google Maps view of the current route order.</p>
      </div>
      <div style={{ height: "420px", borderRadius: "18px", overflow: "hidden" }}>
        <APIProvider apiKey={GOOGLE_MAPS_API_KEY} libraries={["geometry"]}>
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
            <RoutePolyline points={points} stops={stops} routeLegs={routeLegs} />
          </Map>
        </APIProvider>
      </div>
    </section>
  );
}
