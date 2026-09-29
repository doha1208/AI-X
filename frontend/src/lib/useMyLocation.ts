"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { haversineMeters } from "@/lib/geo";
import type { LatLng } from "@/lib/kakao";
import { acceptFix, GEO_OPTIONS, toFix, type Fix } from "@/lib/locationFilter";

const MIN_UPDATE_M = 5;

type MyLocation = { location: LatLng | null; denied: boolean; request: () => void };

// 첫 위치는 기지국·Wi-Fi 기반이라 부정확할 수 있어서 한 번만 받지 않고 계속 지켜보며,
// 더 정확한 GPS 값이 오면 바꾸고 튄 값은 버린다.
export function useMyLocation(): MyLocation {
  const [location, setLocation] = useState<LatLng | null>(null);
  const [denied, setDenied] = useState(false);
  const [watchKey, setWatchKey] = useState(0);
  const lastFixRef = useRef<Fix | null>(null);
  const shownRef = useRef<LatLng | null>(null);
  const supported = typeof navigator !== "undefined" && Boolean(navigator.geolocation);

  // 상태는 위치 콜백 안에서만 바꾼다 — effect 본문에서 바로 setState하지 않도록.
  useEffect(() => {
    if (!navigator.geolocation) return;
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const fix = toFix(pos);
        if (!acceptFix(lastFixRef.current, fix)) return;
        lastFixRef.current = fix;
        // 제자리 떨림마다 지도 오버레이를 다시 그리지 않도록 마지막으로 알린 위치에서 움직였을 때만 알린다.
        const shown = shownRef.current;
        if (shown && haversineMeters(shown, fix) < MIN_UPDATE_M) return;
        shownRef.current = { lat: fix.lat, lng: fix.lng };
        setLocation(shownRef.current);
        setDenied(false);
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) setDenied(true);
      },
      GEO_OPTIONS
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [watchKey]);

  const request = useCallback(() => setWatchKey((k) => k + 1), []);

  return { location, denied: denied || !supported, request };
}
