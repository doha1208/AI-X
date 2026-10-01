"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import type { SafetyZone } from "@/lib/api";
import {
  loadKakaoSdk,
  type KakaoMap,
  type KakaoMouseEvent,
  type KakaoOverlay,
  type LatLng,
} from "@/lib/kakao";
import { LONG_PRESS_DELAY_MS, movedPastLongPressTolerance, supportsMapLongPress, type ScreenPoint } from "@/lib/longPress";
import { parsePx, visibleMapInsets } from "@/lib/mapInsets";

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;
// 기본값을 매번 새 배열로 만들면 오버레이 effect가 렌더마다 다시 돈다.
const EMPTY: never[] = [];
const DEFAULT_CENTER = { lat: 37.5665, lng: 126.978 };
const FOLLOW_LEVEL = 3;
// 하단 시트가 지도를 덮는 폭(globals.css의 모바일 기준과 같다).
const MOBILE_QUERY = "(max-width: 767px)";

type ContextMenuInfo = LatLng & { x: number; y: number };

export type SafetyMapHandle = { zoomIn(): void; zoomOut(): void; panTo(position: LatLng): void };
export type MapLabel = { position: LatLng; text: string; tone: "start" | "end" };

type Props = {
  ref?: Ref<SafetyMapHandle>;
  zones?: SafetyZone[];
  rankedZones?: SafetyZone[];
  bells?: LatLng[];
  center?: LatLng;
  myLocation?: LatLng;
  // 있으면 내 위치 둘레에 GPS 오차 범위 원을 그린다(미터). 길안내 탭만 넘긴다.
  accuracyRadiusM?: number | null;
  routePath?: LatLng[];
  comparePath?: LatLng[];
  labels?: MapLabel[];
  focusZone?: SafetyZone | null;
  followLocation?: boolean;
  onSelect?: (latlng: LatLng) => void;
  onZoneSelect?: (zone: SafetyZone) => void;
  onContextMenu?: (info: ContextMenuInfo) => void;
  height?: number | string;
};

function scoreColor(score: number): string {
  if (score >= 70) return "#2e7d32"; // 안전
  if (score >= 40) return "#f9a825"; // 보통
  return "#c62828"; // 주의
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

const HOUSE_SVG =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="#fff"><path d="M12 3 2 11.5h3V21h5.5v-6h3v6H19v-9.5h3Z"/></svg>';
const WALKER_SVG =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13" cy="4" r="1.6" fill="#fff"/><path d="m9 21 2.5-6.5L14 17v4"/><path d="M7 12.5 9.5 9l3-.5 2.5 3.5 2.5 1"/><path d="m11.5 14.5 1-5.5"/></svg>';

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

function circleElement(size: number, background: string, inner = ""): HTMLDivElement {
  const el = document.createElement("div");
  el.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;background:${background};border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);display:grid;place-items:center;`;
  el.innerHTML = inner;
  return el;
}

function labelElement(label: MapLabel): HTMLDivElement {
  const color = label.tone === "start" ? "#2e7d32" : "#c62828";
  const el = document.createElement("div");
  el.style.cssText = `display:flex;align-items:center;gap:6px;padding:4px 10px;border:2px solid ${color};border-radius:10px;background:#fff;font-size:12px;font-weight:700;color:#1a1a1a;box-shadow:0 2px 6px rgba(0,0,0,0.2);white-space:nowrap;`;
  const dot = document.createElement("span");
  dot.style.cssText = `width:7px;height:7px;border-radius:50%;background:${color};`;
  el.append(dot, label.text);
  return el;
}

export function SafetyMap({
  ref,
  zones = EMPTY,
  rankedZones = EMPTY,
  bells = EMPTY,
  center = DEFAULT_CENTER,
  myLocation,
  accuracyRadiusM,
  routePath,
  comparePath,
  labels = EMPTY,
  focusZone,
  followLocation = false,
  onSelect,
  onZoneSelect,
  onContextMenu,
  height = 400,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KakaoMap | null>(null);
  const overlaysRef = useRef<KakaoOverlay[]>([]);
  // 사용자가 지도를 끌었거나 다른 기능(검색·경로·구역 선택)이 시점을 옮겼으면 더는 내 위치로 끌고 가지 않는다.
  const viewTakenRef = useRef(false);
  const hasFollowZoomedRef = useRef(false);
  const lastFocusDongCodeRef = useRef<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [layoutVersion, setLayoutVersion] = useState(0);
  const onSelectRef = useRef(onSelect);
  const onZoneSelectRef = useRef(onZoneSelect);
  const onContextMenuRef = useRef(onContextMenu);
  const lastContextPos = useRef<{ x: number; y: number } | null>(null);
  const suppressNextClickRef = useRef(false);
  const suppressClickTimerRef = useRef<number | null>(null);
  // 지도 생성 시 한 번만 쓰는 초기 중심. effect 의존성에 center를 넣으면 내 위치가
  // 잡힐 때 cleanup이 우클릭·resize 리스너를 떼고, mapRef 가드 때문에 다시 붙지 않는다.
  const initialCenterRef = useRef(center);
  const [boundaries, setBoundaries] = useState<DongBoundaryMap | null>(null);

  useImperativeHandle(ref, () => ({
    zoomIn: () => mapRef.current?.setLevel(mapRef.current.getLevel() - 1),
    zoomOut: () => mapRef.current?.setLevel(mapRef.current.getLevel() + 1),
    panTo: (position) => {
      viewTakenRef.current = true;
      mapRef.current?.panTo(new window.kakao.maps.LatLng(position.lat, position.lng));
    },
  }), []);

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
    onZoneSelectRef.current = onZoneSelect;
    onContextMenuRef.current = onContextMenu;
  }, [onSelect, onZoneSelect, onContextMenu]);

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
    const { lat, lng } = initialCenterRef.current;
    const map = new kakao.maps.Map(containerRef.current, {
      center: new kakao.maps.LatLng(lat, lng),
      level: 6,
    });
    mapRef.current = map;
    const container = containerRef.current;

    // 주소창·safe area·하단 시트처럼 컨테이너만 변하는 모바일 레이아웃에도
    // 카카오 지도 타일을 재배치한다.
    const relayoutMap = () => {
      map.relayout();
      // 검색 결과·하단 시트로 지도 컨테이너가 변하면 기존 setBounds 결과는
      // 이전 크기를 기준으로 남는다. 경로 bounds effect가 새 가용 영역에서
      // 다시 실행되도록 버전을 올린다.
      setLayoutVersion((version) => version + 1);
    };
    window.addEventListener("resize", relayoutMap);
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(relayoutMap);
    resizeObserver?.observe(container);

    kakao.maps.event.addListener(map, "dragstart", () => {
      viewTakenRef.current = true;
    });

    kakao.maps.event.addListener(map, "click", (mouseEvent: KakaoMouseEvent) => {
      if (suppressNextClickRef.current) {
        suppressNextClickRef.current = false;
        if (suppressClickTimerRef.current !== null) window.clearTimeout(suppressClickTimerRef.current);
        suppressClickTimerRef.current = null;
        return;
      }
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
    container.addEventListener("contextmenu", handleNativeContextMenu, true);

    let longPressTimer: number | null = null;
    let longPressStart: ScreenPoint | null = null;

    function clearLongPress() {
      if (longPressTimer !== null) window.clearTimeout(longPressTimer);
      longPressTimer = null;
      longPressStart = null;
    }

    function handlePointerDown(e: PointerEvent) {
      if (!supportsMapLongPress(e.pointerType, e.isPrimary) || !onContextMenuRef.current) return;
      clearLongPress();
      const start = { x: e.clientX, y: e.clientY };
      longPressStart = start;
      longPressTimer = window.setTimeout(() => {
        if (!longPressStart) return;
        const rect = container.getBoundingClientRect();
        const coords = map
          .getProjection()
          .coordsFromContainerPoint(new kakao.maps.Point(start.x - rect.left, start.y - rect.top));
        suppressNextClickRef.current = true;
        if (suppressClickTimerRef.current !== null) window.clearTimeout(suppressClickTimerRef.current);
        suppressClickTimerRef.current = window.setTimeout(() => {
          suppressNextClickRef.current = false;
          suppressClickTimerRef.current = null;
        }, 800);
        onContextMenuRef.current?.({
          lat: coords.getLat(),
          lng: coords.getLng(),
          x: start.x,
          y: start.y,
        });
        clearLongPress();
      }, LONG_PRESS_DELAY_MS);
    }

    function handlePointerMove(e: PointerEvent) {
      if (longPressStart && movedPastLongPressTolerance(longPressStart, { x: e.clientX, y: e.clientY })) {
        clearLongPress();
      }
    }

    container.addEventListener("pointerdown", handlePointerDown, true);
    container.addEventListener("pointermove", handlePointerMove, true);
    container.addEventListener("pointerup", clearLongPress, true);
    container.addEventListener("pointercancel", clearLongPress, true);

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
      container.removeEventListener("pointerdown", handlePointerDown, true);
      container.removeEventListener("pointermove", handlePointerMove, true);
      container.removeEventListener("pointerup", clearLongPress, true);
      container.removeEventListener("pointercancel", clearLongPress, true);
      clearLongPress();
      if (suppressClickTimerRef.current !== null) window.clearTimeout(suppressClickTimerRef.current);
      suppressClickTimerRef.current = null;
      suppressNextClickRef.current = false;
      window.removeEventListener("resize", relayoutMap);
      resizeObserver?.disconnect();
    };
  }, [loaded]);

  // 일반 모드: 지도 시점을 아무도 옮기지 않은 동안만 내 위치를 따라간다 — 처음 잡힌 부정확한 위치가
  // 정확한 GPS 값으로 교정되면 지도도 따라가고, 사용자가 옮긴 시점은 덮어쓰지 않는다.
  // 따라가기 모드(길안내): 위치가 갱신될 때마다 따라가고, 처음 한 번은 걷기용 배율로 확대한다.
  useEffect(() => {
    const map = mapRef.current;
    if (!loaded || !map || !myLocation) return;
    const { kakao } = window;
    if (followLocation) {
      if (!hasFollowZoomedRef.current) {
        map.setLevel(FOLLOW_LEVEL);
        hasFollowZoomedRef.current = true;
      }
      map.panTo(new kakao.maps.LatLng(myLocation.lat, myLocation.lng));
      return;
    }
    if (viewTakenRef.current) return;
    map.panTo(new kakao.maps.LatLng(myLocation.lat, myLocation.lng));
  }, [loaded, myLocation, followLocation]);

  // 경로가 새로 그려질 때만 경로 전체가 보이게 맞춘다. 위치 갱신마다 맞추면
  // 길안내 중 지도가 계속 경로 전체 화면으로 튀어서 따라가기가 안 된다.
  useEffect(() => {
    const map = mapRef.current;
    if (!loaded || !map || followLocation || !routePath || routePath.length < 2) return;
    const { kakao } = window;
    const bounds = new kakao.maps.LatLngBounds();
    [...routePath, ...(comparePath ?? [])].forEach((p) => bounds.extend(new kakao.maps.LatLng(p.lat, p.lng)));
    // 모바일에서는 하단 시트와 상단 카드가 지도를 덮는다 — 경로가 그 뒤에 숨지 않도록 보이는 영역 기준으로 맞춘다.
    const sheetHeight = parsePx(
      containerRef.current ? getComputedStyle(containerRef.current).getPropertyValue("--adaptive-sheet-height") : ""
    );
    const insets = visibleMapInsets(window.matchMedia(MOBILE_QUERY).matches, sheetHeight);
    map.setBounds(bounds, insets.top, insets.right, insets.bottom, insets.left);
    viewTakenRef.current = true;
  }, [loaded, routePath, comparePath, followLocation, layoutVersion]);

  // 구역 표시/내 위치/경로선은 지도 시점을 건드리지 않고 오버레이만 갱신한다.
  useEffect(() => {
    if (!loaded || !mapRef.current) return;
    const { kakao } = window;
    const map = mapRef.current;

    overlaysRef.current.forEach((overlay) => overlay.setMap(null));
    overlaysRef.current = [];

    function addOverlay(position: LatLng, content: HTMLElement, zIndex: number, yAnchor = 0.5) {
      const overlay = new kakao.maps.CustomOverlay({
        position: new kakao.maps.LatLng(position.lat, position.lng),
        content,
        yAnchor,
        zIndex,
      });
      overlay.setMap(map);
      overlaysRef.current.push(overlay);
    }

    zones.forEach((zone) => {
      const isFocused = focusZone?.dong_code === zone.dong_code;
      // 카카오맵 기본 행정구역 경계선(옅은 회백색 얇은 선)과 비슷한 느낌을 내되,
      // 선택된 구역만 진하게 강조한다.
      const strokeColor = isFocused ? "#1a1a1a" : "#ffffff";
      const strokeWeight = isFocused ? 3 : 1;
      const strokeOpacity = isFocused ? 0.9 : 0.7;
      const fillColor = scoreColor(zone.safety_score);
      const fillOpacity = isFocused ? 0.45 : 0.25;
      const zIndex = isFocused ? 5 : 1;

      const infowindow = new kakao.maps.InfoWindow({
        position: new kakao.maps.LatLng(zone.lat, zone.lng),
        content: `<div style="padding:4px 8px;font-size:12px;">${escapeHtml(zone.dong_name)} (${zone.safety_score.toFixed(0)}점)</div>`,
        removable: false,
      });

      const parts = boundaries?.get(zone.dong_code);
      const shapes: KakaoOverlay[] =
        parts && parts.length > 0
          ? // 실제 행정동 경계 폴리곤으로 그린다. 하천 등으로 갈라진 동은 파트가 여러 개일 수 있다.
            parts.map(
              (rings) =>
                new kakao.maps.Polygon({
                  path: rings.map((ring) => ring.map(([lng, lat]) => new kakao.maps.LatLng(lat, lng))),
                  strokeWeight,
                  strokeColor,
                  strokeOpacity,
                  fillColor,
                  fillOpacity,
                  zIndex,
                })
            )
          : // 경계 데이터가 아직 로드되지 않았거나 없는 동은 원으로 대체 표시한다.
            [
              new kakao.maps.Circle({
                center: new kakao.maps.LatLng(zone.lat, zone.lng),
                radius: isFocused ? 450 : 300,
                strokeWeight,
                strokeColor,
                strokeOpacity,
                fillColor,
                fillOpacity,
                zIndex,
              }),
            ];
      shapes.forEach((shape) => {
        shape.setMap(map);
        overlaysRef.current.push(shape);
        kakao.maps.event.addListener(shape, "mouseover", () => infowindow.open(map));
        kakao.maps.event.addListener(shape, "mouseout", () => infowindow.close());
      });
    });

    rankedZones.forEach((zone) => {
      const pin = circleElement(36, scoreColor(zone.safety_score), HOUSE_SVG);
      pin.title = `${zone.dong_name} ${zone.safety_score.toFixed(0)}점`;
      pin.style.cursor = "pointer";
      pin.addEventListener("click", () => onZoneSelectRef.current?.(zone));
      addOverlay(zone, pin, 8);
    });

    bells.forEach((bell) => {
      // 도심은 비상벨이 촘촘해서 큰 마커면 경로선을 가린다 — 작은 점으로만 표시한다.
      const dot = document.createElement("div");
      dot.title = "안전비상벨";
      dot.style.cssText =
        "width:9px;height:9px;border-radius:50%;background:#f9a825;border:2px solid #fff;box-shadow:0 0 0 1px rgba(230,81,0,0.35);";
      addOverlay(bell, dot, 3);
    });

    if (comparePath && comparePath.length > 1) {
      // 안전 가중 경로가 실제 최단경로와 다르다는 걸 비교해 보여주는 참고선.
      const polyline = new kakao.maps.Polyline({
        path: comparePath.map((p) => new kakao.maps.LatLng(p.lat, p.lng)),
        strokeWeight: 4,
        strokeColor: "#9aa0a6",
        strokeOpacity: 0.9,
        strokeStyle: "shortdash",
      });
      polyline.setMap(map);
      overlaysRef.current.push(polyline);
    }

    if (routePath && routePath.length > 1) {
      const polyline = new kakao.maps.Polyline({
        path: routePath.map((p) => new kakao.maps.LatLng(p.lat, p.lng)),
        strokeWeight: 6,
        strokeColor: "#2e7d32",
        strokeOpacity: 0.95,
        strokeStyle: "solid",
      });
      polyline.setMap(map);
      overlaysRef.current.push(polyline);
    }

    labels.forEach((label) => addOverlay(label.position, labelElement(label), 9, 1.4));

    if (myLocation && accuracyRadiusM) {
      const circle = new kakao.maps.Circle({
        center: new kakao.maps.LatLng(myLocation.lat, myLocation.lng),
        radius: accuracyRadiusM,
        strokeWeight: 1,
        strokeColor: "#4285f4",
        strokeOpacity: 0.5,
        fillColor: "#4285f4",
        fillOpacity: 0.12,
        zIndex: 1,
      });
      circle.setMap(map);
      overlaysRef.current.push(circle);
    }

    if (myLocation) {
      const marker = followLocation
        ? circleElement(30, "#2e7d32", WALKER_SVG)
        : circleElement(16, "#4285f4");
      if (!followLocation) marker.style.boxShadow = "0 0 0 3px rgba(66,133,244,0.35), 0 1px 4px rgba(0,0,0,0.3)";
      addOverlay(myLocation, marker, 10);
    }
  }, [loaded, zones, rankedZones, bells, routePath, comparePath, labels, myLocation, accuracyRadiusM, followLocation, focusZone, boundaries]);

  // focusZone(사용자가 방금 클릭한 구역)이 실제로 바뀌었을 때만 그쪽으로 이동+확대한다.
  useEffect(() => {
    if (!mapRef.current || !focusZone) return;
    if (lastFocusDongCodeRef.current === focusZone.dong_code) return;
    lastFocusDongCodeRef.current = focusZone.dong_code;
    viewTakenRef.current = true;
    const { kakao } = window;
    mapRef.current.setLevel(4);
    mapRef.current.panTo(new kakao.maps.LatLng(focusZone.lat, focusZone.lng));
  }, [focusZone]);

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

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
