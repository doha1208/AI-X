"use client";

import { useEffect, useRef, useState } from "react";
import type { SafetyZone } from "@/lib/api";

declare global {
  interface Window {
    kakao: any;
  }
}

type Props = {
  zones: SafetyZone[];
  center?: { lat: number; lng: number };
};

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;
let sdkLoadPromise: Promise<void> | null = null;

function loadKakaoSdk(): Promise<void> {
  if (window.kakao?.maps?.Map) return Promise.resolve();
  if (sdkLoadPromise) return sdkLoadPromise;

  sdkLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${KAKAO_KEY}&autoload=false`;
    script.onload = () => window.kakao.maps.load(() => resolve());
    script.onerror = (event) => {
      console.error("[SafetyMap] Kakao SDK script load failed", event);
      sdkLoadPromise = null;
      reject(new Error("kakao sdk load failed"));
    };
    document.head.appendChild(script);
  });
  return sdkLoadPromise;
}

function scoreColor(score: number): string {
  if (score >= 70) return "#2e7d32"; // 안전
  if (score >= 40) return "#f9a825"; // 보통
  return "#c62828"; // 주의
}

export function SafetyMap({ zones, center = { lat: 37.5665, lng: 126.978 } }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!KAKAO_KEY) return;
    let cancelled = false;
    loadKakaoSdk()
      .then(() => !cancelled && setLoaded(true))
      .catch(() => !cancelled && setLoadError(true));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!loaded || !containerRef.current) return;
    const { kakao } = window;
    const map = new kakao.maps.Map(containerRef.current, {
      center: new kakao.maps.LatLng(center.lat, center.lng),
      level: 6,
    });

    zones.forEach((zone) => {
      const marker = new kakao.maps.Circle({
        center: new kakao.maps.LatLng(zone.lat, zone.lng),
        radius: 300,
        strokeWeight: 1,
        strokeColor: scoreColor(zone.safety_score),
        fillColor: scoreColor(zone.safety_score),
        fillOpacity: 0.5,
      });
      marker.setMap(map);

      const infowindow = new kakao.maps.InfoWindow({
        content: `<div style="padding:4px 8px;font-size:12px;">${zone.dong_name} (${zone.safety_score.toFixed(1)})</div>`,
      });
      kakao.maps.event.addListener(marker, "mouseover", () =>
        infowindow.open(map, new kakao.maps.CustomOverlay({ position: marker.getPosition() }))
      );
    });
  }, [loaded, zones, center]);

  if (!KAKAO_KEY) {
    return (
      <div style={{ padding: 16, border: "1px dashed #999", borderRadius: 8, color: "#666" }}>
        카카오맵 API 키가 설정되지 않았습니다. 카카오 개발자센터(developers.kakao.com)에서
        JavaScript 키를 발급받아 <code>frontend/.env.local</code>에
        <code> NEXT_PUBLIC_KAKAO_MAP_KEY</code>로 추가해주세요.
      </div>
    );
  }

  if (loadError) {
    return <div style={{ color: "crimson" }}>지도를 불러오지 못했습니다. API 키를 확인해주세요.</div>;
  }

  return <div ref={containerRef} style={{ width: "100%", height: 400, borderRadius: 8 }} />;
}
