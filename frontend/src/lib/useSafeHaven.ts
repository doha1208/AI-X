import { useEffect, useRef, useState } from "react";
import { routeEnvironment, type LiveFacilityReport } from "@/lib/api";
import { haversineMeters } from "@/lib/geo";
import type { LatLng } from "@/lib/kakao";

const REFETCH_MOVE_M = 40;
const REFETCH_MIN_MS = 15_000;
const REQUEST_TIMEOUT_MS = 12_000;

export function shouldRefetch(last: { at: LatLng; ms: number } | null, here: LatLng, nowMs: number): boolean {
  return !last || (haversineMeters(last.at, here) >= REFETCH_MOVE_M && nowMs - last.ms >= REFETCH_MIN_MS);
}

export function liveReportExpiresAt(report: LiveFacilityReport): number {
  return Math.min(Date.parse(report.valid_until), Date.parse(report.evaluated_at) + 60_000);
}

type Evidence = { routeId: string; points: LatLng[]; position: LatLng; report: LiveFacilityReport };
type Route = { routePoints: LatLng[] | undefined; routeId: string };

export function useSafeHaven(position: LatLng | null, active: boolean, { routePoints, routeId }: Route): LiveFacilityReport | null {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const positionRef = useRef(position);
  const wake = useRef<(() => void) | null>(null);
  const lastRequest = useRef(-Infinity);

  useEffect(() => {
    positionRef.current = position;
    wake.current?.();
  }, [position]);

  useEffect(() => {
    if (!active || !routePoints || routePoints.length < 2) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | null = null;
    let requestTimeout: ReturnType<typeof setTimeout> | undefined;
    let current: Evidence | null = null;
    let expiresAt = 0;

    function tick() {
      clearTimeout(timer);
      if (disposed) return;
      const now = Date.now();
      if (current && now >= expiresAt) {
        current = null;
        setEvidence(null);
      }
      const here = positionRef.current;
      const needed = here && (!current || haversineMeters(current.position, here) >= REFETCH_MOVE_M);
      const nextAllowed = lastRequest.current + REFETCH_MIN_MS;
      if (here && needed && !request && now >= nextAllowed) {
        const controller = new AbortController();
        request = controller;
        lastRequest.current = now;
        requestTimeout = setTimeout(() => {
          controller.abort();
          if (request === controller) request = null;
          tick();
        }, REQUEST_TIMEOUT_MS);
        void routeEnvironment(routePoints!, { position: here, signal: controller.signal })
          .then((report) => {
            if (disposed || controller.signal.aborted || request !== controller) return;
            const freshUntil = liveReportExpiresAt(report);
            const point = report.local_environment;
            if (!positionRef.current || haversineMeters(here, positionRef.current) >= REFETCH_MOVE_M
                || !(freshUntil > Date.now())
                || (point && (point.artifact_version !== report.artifact_version
                  || point.assessed_at !== report.evaluated_at || point.period !== report.period))) return;
            current = { routeId, points: routePoints!, position: here, report };
            expiresAt = freshUntil;
            setEvidence(current);
          })
          .catch(() => {})
          .finally(() => {
            if (disposed || request !== controller) return;
            clearTimeout(requestTimeout);
            request = null;
            tick();
          });
      }
      const nextWake = Math.min(current ? expiresAt : Infinity,
        needed && !request ? nextAllowed : Infinity);
      if (Number.isFinite(nextWake)) timer = setTimeout(tick, Math.max(1, nextWake - now));
    }

    wake.current = tick;
    document.addEventListener("visibilitychange", tick);
    timer = setTimeout(tick, 0);
    return () => {
      disposed = true;
      wake.current = null;
      request?.abort();
      clearTimeout(requestTimeout);
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", tick);
      setEvidence(previous => previous?.routeId === routeId ? null : previous);
    };
  }, [active, routeId, routePoints]);

  if (!active || !position || !evidence || evidence.routeId !== routeId || evidence.points !== routePoints
    || haversineMeters(evidence.position, position) >= REFETCH_MOVE_M) return null;
  return evidence.report;
}
