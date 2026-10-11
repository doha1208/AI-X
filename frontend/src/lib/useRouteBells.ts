"use client";

import { useEffect, useRef, useState } from "react";
import { nearbyBells, type RouteAlternative } from "@/lib/api";
import { haversineMeters } from "@/lib/geo";

type Bell = { lat: number; lng: number };
type Point = RouteAlternative["route_points"][number];
const ROUTE_BELL_FETCH_LIMIT = 400;
const ROUTE_BELL_RADIUS_M = 60;

export function useRouteBells(points: Point[] | undefined): Bell[] {
  const [bells, setBells] = useState<Bell[]>([]);
  const requestId = useRef(0);

  useEffect(() => {
    if (!points?.length) return;
    const controller = new AbortController();
    const current = ++requestId.current;
    const lats = points.map((point) => point.lat);
    const lngs = points.map((point) => point.lng);
    const center = { lat: (Math.min(...lats) + Math.max(...lats)) / 2, lng: (Math.min(...lngs) + Math.max(...lngs)) / 2 };
    const radiusKm = (Math.max(...points.map((point) => haversineMeters(center, point))) + 200) / 1000;
    void nearbyBells(center.lat, center.lng, radiusKm, ROUTE_BELL_FETCH_LIMIT, { signal: controller.signal })
      .then((items) => items.filter((bell) => points.some((point) => haversineMeters(bell, point) <= ROUTE_BELL_RADIUS_M)))
      .then((items) => { if (requestId.current === current) setBells(items); })
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === "AbortError") && requestId.current === current) setBells([]);
      });
    return () => controller.abort();
  }, [points]);

  return bells;
}
