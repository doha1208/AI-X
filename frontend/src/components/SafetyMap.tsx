"use client";

import { useEffect, useRef, useState } from "react";
import type { SafetyZone } from "@/lib/api";
import { loadKakaoSdk, type LatLng } from "@/lib/kakao";
import { LocateIcon } from "@/components/icons";

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;

type ContextMenuInfo = LatLng & { x: number; y: number };

type Props = {
  zones: SafetyZone[];
  center?: LatLng;
  myLocation?: LatLng;
  routePath?: LatLng[];
  onSelect?: (latlng: LatLng) => void;
  onContextMenu?: (info: ContextMenuInfo) => void;
  height?: number | string;
};

function scoreColor(score: number): string {
  if (score >= 70) return "#2e7d32"; // 안전
  if (score >= 40) return "#f9a825"; // 보통
  return "#c62828"; // 주의
}

export function SafetyMap({
  zones,
  center = { lat: 37.5665, lng: 126.978 },
  myLocation,
  routePath,
  onSelect,
  onContextMenu,
  height = 400,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const onSelectRef = useRef(onSelect);
  const onContextMenuRef = useRef(onContextMenu);
  const lastContextPos = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    onContextMenuRef.current = onContextMenu;
  }, [onContextMenu]);

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
    mapRef.current = map;

    if (myLocation) {
      const dot = document.createElement("div");
      dot.style.width = "16px";
      dot.style.height = "16px";
      dot.style.borderRadius = "50%";
      dot.style.background = "#4285f4";
      dot.style.border = "3px solid #fff";
      dot.style.boxShadow = "0 0 0 3px rgba(66,133,244,0.35), 0 1px 4px rgba(0,0,0,0.3)";

      new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(myLocation.lat, myLocation.lng),
        content: dot,
        yAnchor: 0.5,
        zIndex: 10,
      }).setMap(map);
    }

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

    if (routePath && routePath.length > 1) {
      const path = routePath.map((p) => new kakao.maps.LatLng(p.lat, p.lng));
      new kakao.maps.Polyline({
        path,
        strokeWeight: 5,
        strokeColor: "#2f6b3a",
        strokeOpacity: 0.9,
        strokeStyle: "solid",
      }).setMap(map);

      const bounds = new kakao.maps.LatLngBounds();
      path.forEach((p: any) => bounds.extend(p));
      map.setBounds(bounds);
    }

    kakao.maps.event.addListener(map, "click", (mouseEvent: any) => {
      onSelectRef.current?.({
        lat: mouseEvent.latLng.getLat(),
        lng: mouseEvent.latLng.getLng(),
      });
    });

    // 네이티브 브라우저 우클릭 메뉴를 막고 화면 좌표를 기록해둔다.
    // capture 단계에서 실행되어 카카오 내부 rightclick 처리보다 먼저 좌표를 확보한다.
    function handleNativeContextMenu(e: MouseEvent) {
      e.preventDefault();
      lastContextPos.current = { x: e.clientX, y: e.clientY };
    }
    const container = containerRef.current;
    container?.addEventListener("contextmenu", handleNativeContextMenu, true);

    kakao.maps.event.addListener(map, "rightclick", (mouseEvent: any) => {
      const pos = lastContextPos.current;
      if (!pos) return;
      onContextMenuRef.current?.({
        lat: mouseEvent.latLng.getLat(),
        lng: mouseEvent.latLng.getLng(),
        x: pos.x,
        y: pos.y,
      });
    });

    return () => {
      container?.removeEventListener("contextmenu", handleNativeContextMenu, true);
    };
  }, [loaded, zones, center, myLocation, routePath]);

  function handleRecenter() {
    if (!mapRef.current || !myLocation) return;
    const { kakao } = window;
    mapRef.current.panTo(new kakao.maps.LatLng(myLocation.lat, myLocation.lng));
  }

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

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%", borderRadius: 8 }} />
      {myLocation && (
        <button
          type="button"
          onClick={handleRecenter}
          aria-label="내 위치로 이동"
          title="내 위치로 이동"
          style={{
            position: "absolute",
            right: 12,
            top: 12,
            zIndex: 20,
            width: 36,
            height: 36,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: "none",
            borderRadius: "50%",
            background: "#fff",
            color: "#4285f4",
            boxShadow: "0 1px 4px rgba(0,0,0,0.3)",
            cursor: "pointer",
          }}
        >
          <LocateIcon size={18} />
        </button>
      )}
    </div>
  );
}
