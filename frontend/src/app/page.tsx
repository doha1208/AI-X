"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { nearbyBells, nearbyZones, residenceRecommend, routeSafety, type RouteResult, type SafetyZone } from "@/lib/api";
import { endSession, getSessionUser } from "@/lib/auth";
import { haversineMeters } from "@/lib/geo";
import { geocodeAddress, reverseGeocode, type LatLng } from "@/lib/kakao";

// 경로 선에서 이만큼(m) 안에 있는 비상벨만 지도에 남긴다 — 그 바깥은 "가는 길"과
// 무관해서 표시하면 오히려 방해된다.
const ROUTE_BELL_RADIUS_M = 60;
// 위 필터를 걸기 전 넉넉히 후보를 받아올 개수. 실제로 남는 건 훨씬 적다.
const ROUTE_BELL_FETCH_LIMIT = 400;

// 경로를 감싸는 원 하나로 후보를 받은 뒤, 실제 경로 선(꼭짓점 기준) 근처만 남긴다.
// 도로망 그래프 노드 간격이 촘촘해서(대부분 수십 m) 꼭짓점까지의 거리로 충분히
// "경로 근처"를 근사할 수 있다 — 선분 대 점 거리 계산까지는 필요 없다.
async function bellsNearRoute(points: LatLng[], signal: AbortSignal): Promise<LatLng[]> {
  if (points.length === 0) return [];
  const lats = points.map((p) => p.lat);
  const lngs = points.map((p) => p.lng);
  const center = {
    lat: (Math.min(...lats) + Math.max(...lats)) / 2,
    lng: (Math.min(...lngs) + Math.max(...lngs)) / 2,
  };
  const farthestM = Math.max(...points.map((p) => haversineMeters(center, p)));
  const radiusKm = (farthestM + 200) / 1000; // 여유를 둬서 경계 근처 벨도 후보에 포함
  const candidates = await nearbyBells(center.lat, center.lng, radiusKm, ROUTE_BELL_FETCH_LIMIT, { signal });
  return candidates.filter((bell) => points.some((p) => haversineMeters(bell, p) <= ROUTE_BELL_RADIUS_M));
}
import { SafetyMap } from "@/components/SafetyMap";
import {
  AlertIcon,
  BellIcon,
  CloseIcon,
  ExpandIcon,
  LogoutIcon,
  MapPinIcon,
  RouteIcon,
  SearchIcon,
  ShieldPinIcon,
  TrophyIcon,
} from "@/components/icons";
import styles from "./page.module.css";

function scoreColor(score: number): string {
  if (score >= 70) return "var(--safe)";
  if (score >= 40) return "var(--caution)";
  return "var(--warning)";
}

// "37.55, 126.92" 같은 위경도 직접 입력도 계속 지원 (지오코딩 실패 대비 폴백).
function parseLatLng(value: string): LatLng | null {
  const parts = value.split(",").map((v) => Number(v.trim()));
  if (parts.length !== 2 || parts.some(Number.isNaN)) return null;
  return { lat: parts[0], lng: parts[1] };
}

type FieldKey = "nearby" | "start" | "end";

const REROUTE_DISTANCE_M = 50;
const REROUTE_MIN_INTERVAL_MS = 5000;
const ARRIVAL_RADIUS_M = 30;

function getGeolocationAvailable() {
  return Boolean(navigator.geolocation);
}

export default function Dashboard() {
  const router = useRouter();
  const [sessionUser, setSessionUser] = useState<{ id: number; email: string } | null | undefined>(undefined);
  const [geolocationAvailable] = useState(
    () => typeof navigator !== "undefined" && getGeolocationAvailable()
  );
  const [recommended, setRecommended] = useState<SafetyZone[]>([]);
  const [nearby, setNearby] = useState<SafetyZone[]>([]);
  const [bells, setBells] = useState<{ lat: number; lng: number }[]>([]);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [selectedAlternativeIndex, setSelectedAlternativeIndex] = useState(0);
  const [selectedZone, setSelectedZone] = useState<SafetyZone | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [myLocation, setMyLocation] = useState<LatLng | null>(null);
  const [pickMode, setPickMode] = useState<FieldKey | null>(null);
  const [mapFullscreen, setMapFullscreen] = useState(false);
  const [locationDenied, setLocationDenied] = useState(false);
  const [contextMenu, setContextMenu] = useState<
    (LatLng & { x: number; y: number; address: string | null; loading: boolean }) | null
  >(null);

  function requestMyLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setMyLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocationDenied(false);
      },
      (err) => {
        console.warn("[geolocation] failed:", err.message);
        setLocationDenied(true);
      }
    );
  }

  const [navigating, setNavigating] = useState(false);
  const destinationRef = useRef<LatLng | null>(null);
  const watchIdRef = useRef<number | null>(null);
  const lastRouteFetchRef = useRef<{ origin: LatLng; at: number } | null>(null);
  const isRefetchingRef = useRef(false);
  const routeRequestRef = useRef<AbortController | null>(null);
  const bellsRequestRef = useRef(0);

  useEffect(() => {
    let active = true;
    void getSessionUser()
      .then((user) => { if (active) setSessionUser(user); })
      .catch(() => { if (active) { setSessionUser(null); router.replace("/login"); } });
    return () => { active = false; };
  }, [router]);

  const activeAlternative = route?.alternatives[selectedAlternativeIndex] ?? route?.alternatives[0] ?? null;

  useEffect(() => {
    if (!activeAlternative) return;
    const controller = new AbortController();
    const requestId = ++bellsRequestRef.current;
    void bellsNearRoute(activeAlternative.route_points, controller.signal)
      .then((nextBells) => {
        if (bellsRequestRef.current === requestId) setBells(nextBells);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (bellsRequestRef.current === requestId) setBells([]);
      });
    return () => controller.abort();
  }, [activeAlternative]);

  function stopNavigation() {
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
    setNavigating(false);
  }

  async function handlePositionUpdate(pos: GeolocationPosition) {
    const here: LatLng = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    setMyLocation(here);
    const destination = destinationRef.current;
    if (!destination) return;

    if (haversineMeters(here, destination) <= ARRIVAL_RADIUS_M) {
      stopNavigation();
      return;
    }

    const last = lastRouteFetchRef.current;
    const movedEnough = !last || haversineMeters(here, last.origin) >= REROUTE_DISTANCE_M;
    const enoughTimePassed = !last || Date.now() - last.at >= REROUTE_MIN_INTERVAL_MS;
    if (!movedEnough || !enoughTimePassed || isRefetchingRef.current) return;

    isRefetchingRef.current = true;
    routeRequestRef.current?.abort();
    const controller = new AbortController();
    routeRequestRef.current = controller;
    try {
      const result = await routeSafety(here.lat, here.lng, destination.lat, destination.lng, {
        includeComparison: false,
        signal: controller.signal,
      });
      if (routeRequestRef.current !== controller) return;
      setRoute(result);
      setSelectedAlternativeIndex(0);
      lastRouteFetchRef.current = { origin: here, at: Date.now() };
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      console.warn("[live-route] recompute failed:", err instanceof Error ? err.message : err);
      // 재계산 실패는 배너로 방해하지 않는다 — 기존 경로를 유지하고 다음 위치 갱신에서 재시도.
    } finally {
      if (routeRequestRef.current === controller) isRefetchingRef.current = false;
    }
  }

  function startNavigation() {
    if (!route || !navigator.geolocation) return;
    const end = (activeAlternative?.route_points ?? route.route_points).at(-1);
    if (!end) return;
    destinationRef.current = { lat: end.lat, lng: end.lng };
    lastRouteFetchRef.current = myLocation ? { origin: myLocation, at: Date.now() } : null;
    setNavigating(true);
    watchIdRef.current = navigator.geolocation.watchPosition(
      handlePositionUpdate,
      (err) => {
        console.warn("[geolocation] watch failed:", err.message);
        setError("실시간 위치를 가져오지 못했어요. 위치 권한을 확인해주세요");
        stopNavigation();
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
    );
  }

  useEffect(() => {
    return () => {
      if (watchIdRef.current !== null) navigator.geolocation.clearWatch(watchIdRef.current);
    };
  }, []);

  const [resolved, setResolved] = useState<Record<FieldKey, LatLng | null>>({
    nearby: null,
    start: null,
    end: null,
  });
  const nearbyInputRef = useRef<HTMLInputElement>(null);
  const startInputRef = useRef<HTMLInputElement>(null);
  const endInputRef = useRef<HTMLInputElement>(null);
  const fieldRefs: Record<FieldKey, React.RefObject<HTMLInputElement | null>> = {
    nearby: nearbyInputRef,
    start: startInputRef,
    end: endInputRef,
  };

  function clearResolved(key: FieldKey) {
    setResolved((r) => (r[key] ? { ...r, [key]: null } : r));
  }

  async function resolveField(key: FieldKey): Promise<LatLng | null> {
    if (resolved[key]) return resolved[key];
    const text = fieldRefs[key].current?.value.trim() ?? "";
    if (!text) return null;
    return parseLatLng(text) ?? geocodeAddress(text);
  }

  async function handleMapPick(latlng: LatLng) {
    if (!pickMode) return;
    const key = pickMode;
    setPickMode(null);
    const label = (await reverseGeocode(latlng.lat, latlng.lng)) ?? `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
    const input = fieldRefs[key].current;
    if (input) input.value = label;
    setResolved((r) => ({ ...r, [key]: latlng }));
  }

  async function handleMapContextMenu(info: LatLng & { x: number; y: number }) {
    setContextMenu({ ...info, address: null, loading: true });
    const address = await reverseGeocode(info.lat, info.lng);
    setContextMenu((cm) => (cm && cm.x === info.x && cm.y === info.y ? { ...cm, address, loading: false } : cm));
  }

  function setFieldFromContextMenu(key: FieldKey) {
    if (!contextMenu) return;
    const { lat, lng, address } = contextMenu;
    const label = address ?? `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    const input = fieldRefs[key].current;
    if (input) input.value = label;
    setResolved((r) => ({ ...r, [key]: { lat, lng } }));
    setContextMenu(null);
  }

  async function searchNearbyFromContextMenu() {
    if (!contextMenu) return;
    const { lat, lng } = contextMenu;
    setFieldFromContextMenu("nearby");
    await runNearbySearch({ lat, lng });
  }

  async function runNearbySearch(coords: LatLng) {
    try {
      setRoute(null);
      setSelectedAlternativeIndex(0);
      setNearby(await nearbyZones(coords.lat, coords.lng, 5));
      // 비상벨은 데이터가 촘촘해서(동 중앙값 약 67m) 좁은 반경만 조회한다.
      nearbyBells(coords.lat, coords.lng, 1).then(setBells).catch(() => setBells([]));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "조회 실패");
    }
  }

  function selectZone(zone: SafetyZone) {
    setSelectedZone(zone);
    document.getElementById("map-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function loadRecommended() {
    residenceRecommend(5)
      .then((zones) => {
        setRecommended(zones);
        setError(null);
      })
      .catch((e) => setError(e.message));
  }

  useEffect(() => {
    if (!sessionUser) return;
    loadRecommended();
    if (geolocationAvailable) requestMyLocation();
  }, [sessionUser, geolocationAvailable]);

  useEffect(() => {
    if (!mapFullscreen && !contextMenu) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setMapFullscreen(false);
      setContextMenu(null);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mapFullscreen, contextMenu]);

  useEffect(() => {
    if (!contextMenu) return;
    function handleOutsideClick() {
      setContextMenu(null);
    }
    const id = window.setTimeout(() => window.addEventListener("click", handleOutsideClick), 0);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("click", handleOutsideClick);
    };
  }, [contextMenu]);

  async function handleNearbySearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const coords = await resolveField("nearby");
    if (!coords) {
      setError("주소를 찾을 수 없어요. 정확한 주소를 입력하거나 지도에서 선택해주세요");
      return;
    }
    await runNearbySearch(coords);
  }

  async function handleRouteSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const [start, end] = await Promise.all([resolveField("start"), resolveField("end")]);
    if (!start || !end) {
      setError("출발지/도착지 주소를 찾을 수 없어요. 정확한 주소를 입력하거나 지도에서 선택해주세요");
      return;
    }
    try {
      stopNavigation();
      routeRequestRef.current?.abort();
      const controller = new AbortController();
      routeRequestRef.current = controller;
      const result = await routeSafety(start.lat, start.lng, end.lat, end.lng, { signal: controller.signal });
      if (routeRequestRef.current !== controller) return;
      setNearby([]);
      setRoute(result);
      setSelectedAlternativeIndex(0);
      setError(null);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "경로 조회 실패");
    }
  }

  async function handleLogout() {
    try {
      await endSession();
    } finally {
      setSessionUser(null);
      router.replace("/login");
    }
  }

  const mapZones = useMemo(
    () =>
      Array.from(
        new Map([...recommended, ...nearby, ...(activeAlternative?.zones_passed ?? route?.zones_passed ?? [])].map((z) => [z.dong_code, z])).values()
      ),
    [recommended, nearby, route, activeAlternative]
  );

  if (sessionUser === undefined || sessionUser === null) return null;
  const displayName = sessionUser.email.split("@")[0] || "회원";

  return (
    <main className={styles.page}>
      <nav className={styles.navbar}>
        <div className={styles.navLeft}>
          <span className={styles.brand}>
            <span className={styles.brandIcon}>
              <ShieldPinIcon size={16} />
            </span>
            안심 거주지
          </span>
          <div className={styles.navLinks}>
            <a className={styles.navLink} href="#map-section">
              안전 지도
            </a>
            <a className={styles.navLink} href="#route-section">
              귀갓길 조회
            </a>
            <span className={styles.navLinkDisabled} title="준비 중">
              마이페이지
            </span>
          </div>
        </div>
        <div className={styles.navRight}>
          <button className={styles.bellButton} type="button" aria-label="알림" title="준비 중">
            <BellIcon size={18} />
            <span className={styles.bellDot} />
          </button>
          <span className={styles.avatar}>{displayName.slice(0, 1).toUpperCase()}</span>
          <button className={styles.logoutButton} onClick={handleLogout}>
            <LogoutIcon size={14} />
            로그아웃
          </button>
        </div>
      </nav>

      {error && !bannerDismissed && (
        <div className={styles.banner}>
          <AlertIcon size={16} />
          {error}
          <button type="button" className={styles.bannerRetry} onClick={loadRecommended}>
            다시 시도
          </button>
          <button
            type="button"
            className={styles.bannerClose}
            aria-label="배너 닫기"
            onClick={() => setBannerDismissed(true)}
          >
            <CloseIcon size={14} />
          </button>
        </div>
      )}

      <div className={styles.shell}>
        <h1 className={styles.greeting}>안녕하세요, {displayName}님 👋</h1>
        <p className={styles.greetingSub}>오늘도 안전한 하루 보내세요. 우리 동네 안전지수를 확인해보세요.</p>

        <div className={styles.layout}>
          <aside className={styles.sidebar}>
            <section className={styles.card}>
              <div className={styles.cardHeaderRow}>
                <h2 className={styles.cardHeader}>
                  <TrophyIcon size={17} />
                  안심 거주지 추천 Top 5
                </h2>
                <span className={styles.viewAllLink}>전체보기</span>
              </div>
              {recommended.length === 0 ? (
                <p className={styles.rankMeta}>추천 데이터를 불러오는 중이에요</p>
              ) : (
                <ul className={styles.rankList}>
                  {recommended.map((z, i) => (
                    <li
                      key={z.dong_code}
                      className={`${styles.rankItem} ${selectedZone?.dong_code === z.dong_code ? styles.rankItemSelected : ""}`}
                      onClick={() => selectZone(z)}
                    >
                      <span className={styles.rankNumber}>{i + 1}</span>
                      <span className={styles.rankInfo}>
                        <div className={styles.rankName}>{z.dong_name}</div>
                      </span>
                      <span className={styles.scoreBadge} style={{ background: scoreColor(z.safety_score) }}>
                        {z.safety_score.toFixed(0)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className={styles.card}>
              <h2 className={styles.cardHeader}>
                <SearchIcon size={17} />
                주변 안전 구역 검색
              </h2>
              <form onSubmit={handleNearbySearch} className={styles.searchRow}>
                <input
                  ref={nearbyInputRef}
                  className={styles.searchInput}
                  type="text"
                  placeholder="예: 서울시 마포구 연남동"
                  onChange={() => clearResolved("nearby")}
                  required
                />
                <button type="submit" className={styles.iconButton} aria-label="검색하기">
                  <SearchIcon size={16} />
                </button>
              </form>
              <div className={styles.hintRow}>
                <p className={styles.searchHint}>주소로 검색해보세요</p>
                <button
                  type="button"
                  className={`${styles.pickLink} ${pickMode === "nearby" ? styles.pickLinkActive : ""}`}
                  onClick={() => setPickMode((m) => (m === "nearby" ? null : "nearby"))}
                >
                  <MapPinIcon size={12} />
                  지도에서 선택
                </button>
              </div>
              {nearby.length > 0 && (
                <ul className={styles.miniList}>
                  {nearby.map((z) => (
                    <li
                      key={z.dong_code}
                      className={`${styles.miniItem} ${selectedZone?.dong_code === z.dong_code ? styles.miniItemSelected : ""}`}
                      onClick={() => selectZone(z)}
                    >
                      <span>{z.dong_name}</span>
                      <span className={styles.scoreBadge} style={{ background: scoreColor(z.safety_score) }}>
                        {z.safety_score.toFixed(0)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section id="route-section" className={styles.card}>
              <h2 className={styles.cardHeader}>
                <RouteIcon size={17} />
                귀갓길 안전도 조회
              </h2>
              <form onSubmit={handleRouteSearch} className={styles.formStack}>
                <div className={styles.addressFieldRow}>
                  <div className={styles.addressField}>
                    <span className={styles.addressIcon}>
                      <MapPinIcon size={16} />
                    </span>
                    <input
                      ref={startInputRef}
                      className={styles.addressInput}
                      type="text"
                      placeholder="출발지 주소를 입력하세요"
                      onChange={() => clearResolved("start")}
                      required
                    />
                  </div>
                  <button
                    type="button"
                    className={`${styles.pickLink} ${pickMode === "start" ? styles.pickLinkActive : ""}`}
                    onClick={() => setPickMode((m) => (m === "start" ? null : "start"))}
                  >
                    <MapPinIcon size={12} />
                    지도에서 선택
                  </button>
                </div>
                <div className={styles.addressFieldRow}>
                  <div className={styles.addressField}>
                    <span className={styles.addressIcon}>
                      <MapPinIcon size={16} />
                    </span>
                    <input
                      ref={endInputRef}
                      className={styles.addressInput}
                      type="text"
                      placeholder="도착지 주소를 입력하세요"
                      onChange={() => clearResolved("end")}
                      required
                    />
                  </div>
                  <button
                    type="button"
                    className={`${styles.pickLink} ${pickMode === "end" ? styles.pickLinkActive : ""}`}
                    onClick={() => setPickMode((m) => (m === "end" ? null : "end"))}
                  >
                    <MapPinIcon size={12} />
                    지도에서 선택
                  </button>
                </div>
                <button type="submit" className={styles.primaryButton}>
                  안전도 조회
                </button>
              </form>
            </section>
          </aside>

          <div className={styles.main}>
            <section id="map-section" className={`${styles.card} ${styles.mapCard}`}>
              <div className={styles.mapHeader}>
                <h2 className={styles.cardHeader} style={{ marginBottom: 0 }}>
                  안전지수 지도
                </h2>
                <div className={styles.mapHeaderRight}>
                  <div className={styles.legend}>
                    <span>
                      <span className={styles.legendDot} style={{ background: "var(--safe)" }} />
                      안전 (70+)
                    </span>
                    <span>
                      <span className={styles.legendDot} style={{ background: "var(--caution)" }} />
                      보통 (40~69)
                    </span>
                    <span>
                      <span className={styles.legendDot} style={{ background: "var(--warning)" }} />
                      주의 (40 미만)
                    </span>
                  </div>
                  <button
                    type="button"
                    className={styles.mapExpandButton}
                    onClick={() => setMapFullscreen(true)}
                    aria-label="지도 크게 보기"
                    title="지도 크게 보기"
                  >
                    <ExpandIcon size={16} />
                  </button>
                </div>
              </div>
              {pickMode && (
                <p className={styles.pickModeHint}>
                  지도를 클릭해서 {pickMode === "nearby" ? "검색 위치를" : pickMode === "start" ? "출발지를" : "도착지를"} 선택하세요
                </p>
              )}
              {(locationDenied || !geolocationAvailable) && !myLocation && (
                <p className={styles.locationHint}>
                  내 위치를 가져오지 못했어요. 브라우저 주소창의 위치 권한을 허용한 뒤{" "}
                  <button type="button" className={styles.pickLink} onClick={requestMyLocation}>
                    다시 시도
                  </button>
                </p>
              )}
              <div className={styles.mapBody}>
                <SafetyMap
                  zones={mapZones}
                  bells={bells}
                  center={myLocation ?? undefined}
                  myLocation={myLocation ?? undefined}
                  routePath={activeAlternative?.route_points ?? route?.route_points}
                  comparePath={route?.shortest_route_points ?? undefined}
                  focusZone={selectedZone}
                  onSelect={handleMapPick}
                  onContextMenu={handleMapContextMenu}
                />
              </div>
            </section>

            {mapFullscreen && (
              <div className={styles.mapOverlay} onClick={() => setMapFullscreen(false)}>
                <div className={styles.mapOverlayCard} onClick={(e) => e.stopPropagation()}>
                  <div className={styles.mapOverlayHeader}>
                    <h2 className={styles.cardHeader} style={{ marginBottom: 0 }}>
                      안전지수 지도
                    </h2>
                    <button
                      type="button"
                      className={styles.mapExpandButton}
                      onClick={() => setMapFullscreen(false)}
                      aria-label="닫기"
                      title="닫기"
                    >
                      <CloseIcon size={16} />
                    </button>
                  </div>
                  {pickMode && (
                    <p className={styles.pickModeHint}>
                      지도를 클릭해서 {pickMode === "nearby" ? "검색 위치를" : pickMode === "start" ? "출발지를" : "도착지를"} 선택하세요
                    </p>
                  )}
                  <div className={styles.mapOverlayBody}>
                    <SafetyMap
                      zones={mapZones}
                      bells={bells}
                      center={myLocation ?? undefined}
                      myLocation={myLocation ?? undefined}
                      routePath={activeAlternative?.route_points ?? route?.route_points}
                      comparePath={route?.shortest_route_points ?? undefined}
                      focusZone={selectedZone}
                      onSelect={handleMapPick}
                      onContextMenu={handleMapContextMenu}
                      height="100%"
                    />
                  </div>
                </div>
              </div>
            )}

            <section className={styles.card}>
              {route ? (
                <>
                  <h2 className={styles.cardHeader}>경로 안전도 결과</h2>
                  <p className={styles.routeModeHint}>
                    {route.mode === "safety_weighted"
                      ? "안전점수를 반영한 최적 경로예요"
                      : route.mode === "tmap"
                        ? "실제 도보 최단경로 기준(안전 가중치 미반영)"
                        : "실제 경로를 가져오지 못해 직선 거리로 추정했어요"}
                  </p>
                  {route.shortest_route_points && (
                    <p className={styles.routeModeHint}>
                      지도의 초록 실선이 안전 경로, 회색 점선이 최단경로예요 — 서로 다른 길이면 안전 가중치가 실제로 반영된 거예요
                    </p>
                  )}
                  {route.alternatives.length > 1 && (
                    <div className={styles.alternativeList} aria-label="대안 경로 선택">
                      {route.alternatives.map((alternative, index) => (
                        <button
                          key={`${alternative.distance_m}-${index}`}
                          type="button"
                          className={`${styles.alternativeCard} ${activeAlternative === alternative ? styles.alternativeCardActive : ""}`}
                          onClick={() => setSelectedAlternativeIndex(index)}
                        >
                          <span>경로 {index + 1}</span>
                          <strong>{alternative.safety_score.toFixed(0)}점 · {(alternative.distance_m / 1000).toFixed(1)}km</strong>
                        </button>
                      ))}
                    </div>
                  )}
                  <div className={styles.navToggleRow}>
                    {navigating ? (
                      <>
                        <span className={styles.liveBadge}>
                          <span className={styles.liveDot} /> 실시간 안내 중
                        </span>
                        <button type="button" className={styles.navStopButton} onClick={stopNavigation}>
                          중지
                        </button>
                      </>
                    ) : (
                      <button type="button" className={styles.navStartButton} onClick={startNavigation}>
                        실시간 안내 시작
                      </button>
                    )}
                  </div>
                  <div className={styles.resultSummary}>
                    <span>경로 전체 안전지수</span>
                    <strong>{(activeAlternative?.safety_score ?? route.safety_score).toFixed(0)}점</strong>
                  </div>
                  <p className={styles.routeModeHint}>거리 {((activeAlternative?.distance_m ?? 0) / 1000).toFixed(1)}km</p>
                  <ul className={styles.rankList}>
                    {(activeAlternative?.zones_passed ?? route.zones_passed).map((z) => (
                      <li key={z.dong_code} className={styles.rankItem}>
                        <span className={styles.rankInfo}>
                          <div className={styles.rankName}>{z.dong_name}</div>
                        </span>
                        <span className={styles.scoreBadge} style={{ background: scoreColor(z.safety_score) }}>
                          {z.safety_score.toFixed(0)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <div className={styles.emptyState}>
                  <span className={styles.emptyIcon}>
                    <MapPinIcon size={20} />
                  </span>
                  <span className={styles.emptyTitle}>아직 검색 결과가 없어요</span>
                  <span>주소를 입력하거나 지도를 움직여서 주변 안전 구역을 확인해보세요</span>
                </div>
              )}
            </section>
          </div>
        </div>

        <footer className={styles.footer}>
          © 2026 안심 거주지. 모두의 안전한 일상을 응원합니다.
          <div className={styles.footerLinks}>
            <span>이용약관</span>
            <span>개인정보처리방침</span>
            <span>고객센터</span>
          </div>
        </footer>
      </div>

      {contextMenu && (
        <div
          className={styles.contextMenu}
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <p className={styles.contextMenuAddress}>
            {contextMenu.loading
              ? "주소를 찾는 중..."
              : contextMenu.address ?? `${contextMenu.lat.toFixed(5)}, ${contextMenu.lng.toFixed(5)}`}
          </p>
          <button type="button" className={styles.contextMenuItem} onClick={() => setFieldFromContextMenu("start")}>
            출발지로 설정
          </button>
          <button type="button" className={styles.contextMenuItem} onClick={() => setFieldFromContextMenu("end")}>
            도착지로 설정
          </button>
          <button type="button" className={styles.contextMenuItem} onClick={searchNearbyFromContextMenu}>
            이 위치 주변 안전구역 검색
          </button>
        </div>
      )}
    </main>
  );
}
