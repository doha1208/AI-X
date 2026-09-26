"use client";

import { useEffect, useRef, useState } from "react";
import type { SafetyZone } from "@/lib/api";
import {
  loadKakaoSdk,
  type KakaoMap,
  type KakaoMouseEvent,
  type KakaoOverlay,
  type LatLng,
} from "@/lib/kakao";
import { LocateIcon } from "@/components/icons";

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;

type ContextMenuInfo = LatLng & { x: number; y: number };

type Props = {
  zones: SafetyZone[];
  bells?: LatLng[];
  center?: LatLng;
  myLocation?: LatLng;
  routePath?: LatLng[];
  comparePath?: LatLng[];
  focusZone?: SafetyZone | null;
  onSelect?: (latlng: LatLng) => void;
  onContextMenu?: (info: ContextMenuInfo) => void;
  height?: number | string;
};

function scoreColor(score: number): string {
  if (score >= 70) return "#2e7d32"; // 안전
  if (score >= 40) return "#f9a825"; // 보통
  return "#c62828"; // 주의
}

type DongBoundaryGeoJson = {
  features: {
    properties: { adm_cd2: string };
    geometry: { type: "Polygon" | "MultiPolygon"; coordinates: number[][][] | number[][][][] };
  }[];
};

// dong_code -> 폴리곤 파트 목록(파트마다 [외곽선, 구멍1, 구멍2, ...] 좌표 링).
// 동이 여러 조각(하천으로 나뉜 섬 등)으로 나뉘면 파트가 여러 개일 수 있다.
type DongBoundaryMap = Map<string, number[][][][]>;

let boundaryCache: Promise<DongBoundaryMap> | null = null;

const BOUNDARY_FILES = ["/data/seoul-dong-boundaries.geojson", "/data/gyeonggi-dong-boundaries.geojson"];

// 파일 하나가 실패해도 다른 지역 경계는 살린다 — 실패한 지역만 원(circle) 폴백으로 그려진다.
async function fetchBoundaryFeatures(url: string): Promise<DongBoundaryGeoJson["features"]> {
  try {
    const res = await fetch(url);
    return ((await res.json()) as DongBoundaryGeoJson).features;
  } catch {
    return [];
  }
}

function loadDongBoundaries(): Promise<DongBoundaryMap> {
  if (!boundaryCache) {
    boundaryCache = Promise.all(BOUNDARY_FILES.map(fetchBoundaryFeatures)).then((files) => {
      const map: DongBoundaryMap = new Map();
      files.flat().forEach((feature) => {
        const code = feature.properties.adm_cd2;
        const parts: number[][][][] =
          feature.geometry.type === "Polygon"
            ? [feature.geometry.coordinates as number[][][]]
            : (feature.geometry.coordinates as number[][][][]);
        map.set(code, parts);
      });
      return map;
    });
  }
  return boundaryCache;
}

export function SafetyMap({
  zones,
  bells = [],
  center = { lat: 37.5665, lng: 126.978 },
  myLocation,
  routePath,
  comparePath,
  focusZone,
  onSelect,
  onContextMenu,
  height = 400,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KakaoMap | null>(null);
  const overlaysRef = useRef<KakaoOverlay[]>([]);
  const hasAutoCenteredRef = useRef(false);
  const lastFocusDongCodeRef = useRef<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const onSelectRef = useRef(onSelect);
  const onContextMenuRef = useRef(onContextMenu);
  const lastContextPos = useRef<{ x: number; y: number } | null>(null);
  const [boundaries, setBoundaries] = useState<DongBoundaryMap | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadDongBoundaries().then((map) => {
      if (!cancelled) setBoundaries(map);
    });
    return () => {
      cancelled = true;
    };
  }, []);

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

  // 지도 인스턴스는 처음 한 번만 생성한다. zones/focusZone 같은 데이터가
  // 바뀔 때마다 재생성하면 사용자가 드래그/줌 해둔 시점이 매번 리셋된다.
  useEffect(() => {
    if (!loaded || !containerRef.current || mapRef.current) return;
    const { kakao } = window;
    const map = new kakao.maps.Map(containerRef.current, {
      center: new kakao.maps.LatLng(center.lat, center.lng),
      level: 6,
    });
    mapRef.current = map;

    // 브라우저 창 크기가 바뀌면 컨테이너 크기도 바뀌므로 Kakao 지도에 재계산을 알려준다.
    const relayoutMap = () => map.relayout();
    window.addEventListener("resize", relayoutMap);

    kakao.maps.event.addListener(map, "click", (mouseEvent: KakaoMouseEvent) => {
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
    container.addEventListener("contextmenu", handleNativeContextMenu, true);

    kakao.maps.event.addListener(map, "rightclick", (mouseEvent: KakaoMouseEvent) => {
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
      container.removeEventListener("contextmenu", handleNativeContextMenu, true);
      window.removeEventListener("resize", relayoutMap);
    };
  }, [loaded, center.lat, center.lng]);

  // 내 위치를 처음 얻었을 때 한 번만 그쪽으로 이동한다. 이후 위치가 갱신돼도
  // 사용자가 지도를 옮겨둔 상태를 덮어쓰지 않는다(재이동은 "내 위치로" 버튼으로).
  useEffect(() => {
    if (!mapRef.current || !myLocation || hasAutoCenteredRef.current) return;
    const { kakao } = window;
    mapRef.current.panTo(new kakao.maps.LatLng(myLocation.lat, myLocation.lng));
    hasAutoCenteredRef.current = true;
  }, [myLocation]);

  // 구역 표시/내 위치 점/경로선은 지도 시점을 건드리지 않고 오버레이만 갱신한다.
  useEffect(() => {
    if (!loaded || !mapRef.current) return;
    const { kakao } = window;
    const map = mapRef.current;

    overlaysRef.current.forEach((overlay) => overlay.setMap(null));
    overlaysRef.current = [];

    if (myLocation) {
      const dot = document.createElement("div");
      dot.style.width = "16px";
      dot.style.height = "16px";
      dot.style.borderRadius = "50%";
      dot.style.background = "#4285f4";
      dot.style.border = "3px solid #fff";
      dot.style.boxShadow = "0 0 0 3px rgba(66,133,244,0.35), 0 1px 4px rgba(0,0,0,0.3)";

      const dotOverlay = new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(myLocation.lat, myLocation.lng),
        content: dot,
        yAnchor: 0.5,
        zIndex: 10,
      });
      dotOverlay.setMap(map);
      overlaysRef.current.push(dotOverlay);
    }

    zones.forEach((zone) => {
      const isFocused = focusZone?.dong_code === zone.dong_code;
      // 카카오맵 기본 행정구역 경계선(옅은 회백색 얇은 선)과 비슷한 느낌을 내되,
      // 선택된 구역만 진하게 강조한다.
      const strokeColor = isFocused ? "#1a1a1a" : "#ffffff";
      const strokeWeight = isFocused ? 3 : 1;
      const strokeOpacity = isFocused ? 0.9 : 0.7;
      const fillColor = scoreColor(zone.safety_score);
      const fillOpacity = isFocused ? 0.55 : 0.32;
      const zIndex = isFocused ? 5 : 1;

      const infowindow = new kakao.maps.InfoWindow({
        position: new kakao.maps.LatLng(zone.lat, zone.lng),
        content: `<div style="padding:4px 8px;font-size:12px;">${zone.dong_name} (${zone.safety_score.toFixed(1)})</div>`,
        removable: false,
      });

      const parts = boundaries?.get(zone.dong_code);

      if (parts && parts.length > 0) {
        // 실제 행정동 경계 폴리곤으로 그린다. 하천 등으로 갈라진 동은 파트가 여러 개일 수 있다.
        parts.forEach((rings) => {
          const path = rings.map((ring) => ring.map(([lng, lat]) => new kakao.maps.LatLng(lat, lng)));
          const polygon = new kakao.maps.Polygon({
            path,
            strokeWeight,
            strokeColor,
            strokeOpacity,
            fillColor,
            fillOpacity,
            zIndex,
          });
          polygon.setMap(map);
          overlaysRef.current.push(polygon);
          kakao.maps.event.addListener(polygon, "mouseover", () => infowindow.open(map));
          kakao.maps.event.addListener(polygon, "mouseout", () => infowindow.close());
        });
      } else {
        // 경계 데이터가 아직 로드되지 않았거나 없는 동은 원으로 대체 표시한다.
        const circle = new kakao.maps.Circle({
          center: new kakao.maps.LatLng(zone.lat, zone.lng),
          radius: isFocused ? 450 : 300,
          strokeWeight,
          strokeColor,
          strokeOpacity,
          fillColor,
          fillOpacity,
          zIndex,
        });
        circle.setMap(map);
        overlaysRef.current.push(circle);
        kakao.maps.event.addListener(circle, "mouseover", () => infowindow.open(map));
        kakao.maps.event.addListener(circle, "mouseout", () => infowindow.close());
      }
    });

    bells.forEach((bell) => {
      // 도심은 비상벨이 촘촘해서(백엔드가 가까운 순 최대 60개로 제한해도) 큰 마커면
      // 경로선을 가린다 — 작은 점으로만 위치를 표시하고, 이름은 hover 시 title로.
      const marker = document.createElement("div");
      marker.title = "안전비상벨";
      marker.style.width = "8px";
      marker.style.height = "8px";
      marker.style.borderRadius = "50%";
      marker.style.background = "#e65100";
      marker.style.border = "1px solid #fff";
      marker.style.boxShadow = "0 0 0 1px rgba(230,81,0,0.4)";

      const overlay = new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(bell.lat, bell.lng),
        content: marker,
        yAnchor: 0.5,
        zIndex: 3,
      });
      overlay.setMap(map);
      overlaysRef.current.push(overlay);
    });

    if (comparePath && comparePath.length > 1) {
      // 안전 가중 경로가 실제 최단경로와 다르다는 걸 비교해 보여주는 참고선.
      const path = comparePath.map((p) => new kakao.maps.LatLng(p.lat, p.lng));
      const polyline = new kakao.maps.Polyline({
        path,
        strokeWeight: 4,
        strokeColor: "#888888",
        strokeOpacity: 0.8,
        strokeStyle: "shortdash",
      });
      polyline.setMap(map);
      overlaysRef.current.push(polyline);
    }

    if (routePath && routePath.length > 1) {
      const path = routePath.map((p) => new kakao.maps.LatLng(p.lat, p.lng));
      const polyline = new kakao.maps.Polyline({
        path,
        strokeWeight: 5,
        strokeColor: "#2f6b3a",
        strokeOpacity: 0.9,
        strokeStyle: "solid",
      });
      polyline.setMap(map);
      overlaysRef.current.push(polyline);

      const bounds = new kakao.maps.LatLngBounds();
      path.forEach((p) => bounds.extend(p));
      if (comparePath) comparePath.forEach((p) => bounds.extend(new kakao.maps.LatLng(p.lat, p.lng)));
      map.setBounds(bounds);
    }
  }, [loaded, zones, bells, routePath, comparePath, myLocation, focusZone, boundaries]);

  // focusZone(사용자가 방금 클릭한 구역)이 실제로 바뀌었을 때만 그쪽으로 이동+확대한다.
  useEffect(() => {
    if (!mapRef.current || !focusZone) return;
    if (lastFocusDongCodeRef.current === focusZone.dong_code) return;
    lastFocusDongCodeRef.current = focusZone.dong_code;
    const { kakao } = window;
    mapRef.current.setLevel(4);
    mapRef.current.panTo(new kakao.maps.LatLng(focusZone.lat, focusZone.lng));
  }, [focusZone]);

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
