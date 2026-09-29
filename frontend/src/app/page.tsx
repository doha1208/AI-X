"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { nearbyBells, nearbyZones, residenceRecommend, type SafetyZone } from "@/lib/api";
import { haversineMeters } from "@/lib/geo";
import { reverseGeocode, type LatLng } from "@/lib/kakao";
import { placeFromQuery, placeQuery, resolvePlace, type Place } from "@/lib/place";
import { addRecent, loadSettings } from "@/lib/preferences";
import { useMyLocation } from "@/lib/useMyLocation";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import { AppHeader } from "@/components/AppHeader";
import { SafetyMap, type SafetyMapHandle } from "@/components/SafetyMap";
import { MapContextMenu, MapControls, MapLegend, useMapContextMenu } from "@/components/MapOverlays";
import { withSearch } from "@/components/WithSearch";
import { AlertIcon, CloseIcon, SearchIcon } from "@/components/icons";
import styles from "./page.module.css";

const NEARBY_RADIUS_KM = 5;
const TOP_NEARBY = 5;
const TOP_ALL = 10;

const SAFETY_LEGEND = [
  { label: "안전 (70~100)", swatch: "dot" as const, color: "var(--safe)" },
  { label: "보통 (40~69)", swatch: "dot" as const, color: "var(--caution)" },
  { label: "주의 (0~39)", swatch: "dot" as const, color: "var(--warning)" },
];

function scoreTone(score: number): string {
  if (score >= 70) return styles.scoreSafe;
  if (score >= 40) return styles.scoreCaution;
  return styles.scoreWarning;
}

type Nearby = { place: Place; zones: SafetyZone[] };

export default withSearch(ResidencePage);

function ResidencePage({ search }: { search: string }) {
  const router = useRouter();
  const user = useSessionUser();
  const { location, request: requestLocation } = useMyLocation();
  const mapRef = useRef<SafetyMapHandle>(null);
  const menu = useMapContextMenu();
  const [settings] = useState(loadSettings);
  const [initialNear] = useState(() => placeFromQuery(search, "near"));
  const [query, setQuery] = useState(initialNear?.label ?? "");
  const [allRanking, setAllRanking] = useState<SafetyZone[] | null>(null);
  const [nearby, setNearby] = useState<Nearby | null>(null);
  const [scope, setScope] = useState<"nearby" | "all">(initialNear ? "nearby" : "all");
  const [bells, setBells] = useState<LatLng[]>([]);
  const [selectedZone, setSelectedZone] = useState<SafetyZone | null>(null);
  const [picking, setPicking] = useState(false);
  const [searching, setSearching] = useState(initialNear !== null);
  const [error, setError] = useState<string | null>(null);

  function searchAt(place: Place) {
    setSearching(true);
    setError(null);
    return loadNearby(place);
  }

  // 상태 변경은 모두 await 이후에만 한다 — 처음 쿼리로 들어온 위치를 effect에서 바로 불러오기 때문.
  async function loadNearby(place: Place) {
    try {
      const zones = await nearbyZones(place.lat, place.lng, NEARBY_RADIUS_KM);
      setNearby({ place, zones });
      setScope("nearby");
      setSelectedZone(null);
      mapRef.current?.panTo(place);
      const closest = zones.reduce<SafetyZone | null>(
        (best, z) => (!best || haversineMeters(place, z) < haversineMeters(place, best) ? z : best),
        null
      );
      if (closest) addRecent("searches", closest.dong_name);
      // 비상벨은 데이터가 촘촘해서(동 중앙값 약 67m) 좁은 반경만 조회한다.
      if (settings.showBells) {
        nearbyBells(place.lat, place.lng, 1).then(setBells).catch(() => setBells([]));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "주변 안전 구역을 불러오지 못했어요");
    } finally {
      setSearching(false);
    }
  }

  useEffect(() => {
    residenceRecommend(TOP_ALL)
      .then(setAllRanking)
      .catch((err) => setError(err instanceof Error ? err.message : "추천 목록을 불러오지 못했어요"));
  }, []);

  useEffect(() => {
    if (initialNear) void loadNearby(initialNear);
    // 쿼리로 넘어온 위치는 처음 한 번만 검색한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const place = await resolvePlace(query);
    if (!place) {
      setError("주소를 찾을 수 없어요. 정확한 주소를 입력하거나 지도에서 선택해주세요");
      return;
    }
    await searchAt(place);
  }

  function searchMyLocation() {
    if (!location) {
      requestLocation();
      setError("내 위치를 가져오지 못했어요. 브라우저의 위치 권한을 허용해주세요");
      return;
    }
    setQuery("현재 위치");
    void searchAt({ ...location, label: "현재 위치" });
  }

  async function handleMapPick(latlng: LatLng) {
    if (!picking) return;
    setPicking(false);
    const label = (await reverseGeocode(latlng.lat, latlng.lng)) ?? `${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}`;
    setQuery(label);
    await searchAt({ ...latlng, label });
  }

  const showingNearby = scope === "nearby" && nearby !== null;
  // 매 렌더마다 새 배열을 만들면 지도 오버레이가 키 입력마다 다시 그려진다.
  const ranking = useMemo(
    () =>
      showingNearby
        ? [...nearby.zones].sort((a, b) => b.safety_score - a.safety_score).slice(0, TOP_NEARBY)
        : (allRanking ?? []),
    [showingNearby, nearby, allRanking]
  );

  if (!user) return null;
  const loadingList = showingNearby ? searching : allRanking === null;

  return (
    <main className={styles.page}>
      <AppHeader userInitial={userInitial(user)} />

      <div className={styles.stage}>
        <SafetyMap
          ref={mapRef}
          zones={showingNearby ? nearby.zones : ranking}
          rankedZones={ranking}
          bells={settings.showBells ? bells : undefined}
          center={location ?? undefined}
          myLocation={location ?? undefined}
          focusZone={selectedZone}
          onSelect={handleMapPick}
          onZoneSelect={setSelectedZone}
          onContextMenu={menu.open}
          height="100%"
        />

        <form className={styles.searchBar} onSubmit={handleSearch} role="search">
          <SearchIcon size={18} className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="동네나 주소를 검색하세요 (예: 수원시 영통구 망포동)"
            aria-label="주소 검색"
          />
          <button
            type="button"
            className={`${styles.chip} ${picking ? styles.chipActive : ""}`}
            onClick={() => setPicking((p) => !p)}
            aria-pressed={picking}
          >
            지도에서 선택
          </button>
          <button type="button" className={styles.primaryChip} onClick={searchMyLocation}>
            현재 위치
          </button>
        </form>

        {(error || picking) && (
          <div className={`${styles.notice} ${error ? styles.noticeError : ""}`} role={error ? "alert" : "status"}>
            {error ? <AlertIcon size={16} /> : null}
            {error ?? "지도를 클릭해서 검색할 위치를 선택하세요"}
            <button
              type="button"
              className={styles.noticeClose}
              aria-label="닫기"
              onClick={() => (error ? setError(null) : setPicking(false))}
            >
              <CloseIcon size={14} />
            </button>
          </div>
        )}

        <section className={styles.panel} aria-label="안심 거주지 순위">
          <header className={styles.panelHeader}>
            <h1 className={styles.panelTitle}>{showingNearby ? "안심 거주지 추천 Top 5" : "전체 지역 안심 순위"}</h1>
            <p className={styles.panelSub}>
              {showingNearby ? `${nearby.place.label} 반경 ${NEARBY_RADIUS_KM}km 기준` : `안전지수 상위 ${TOP_ALL}곳`}
            </p>
          </header>

          {loadingList ? (
            <p className={styles.panelEmpty}>불러오는 중...</p>
          ) : ranking.length === 0 ? (
            <p className={styles.panelEmpty}>이 주변에서 안전 구역을 찾지 못했어요. 다른 위치를 검색해보세요.</p>
          ) : (
            <ol className={styles.rankList}>
              {ranking.map((zone, i) => (
                <li key={zone.dong_code}>
                  <button
                    type="button"
                    className={`${styles.rankItem} ${selectedZone?.dong_code === zone.dong_code ? styles.rankItemActive : ""}`}
                    onClick={() => setSelectedZone(zone)}
                  >
                    <span className={`${styles.rankNumber} ${i === 0 ? styles.rankFirst : ""}`}>{i + 1}</span>
                    <span className={styles.rankName}>{zone.dong_name}</span>
                    <span className={`${styles.scoreBadge} ${scoreTone(zone.safety_score)}`}>
                      {zone.safety_score.toFixed(0)}점
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}

          <footer className={styles.panelFooter}>
            {showingNearby ? (
              <button type="button" className={styles.footerButton} onClick={() => setScope("all")}>
                전체 지역 순위 보기
              </button>
            ) : nearby ? (
              <button type="button" className={styles.footerButton} onClick={() => setScope("nearby")}>
                {nearby.place.label} 주변 순위 보기
              </button>
            ) : (
              <button type="button" className={styles.footerButton} onClick={searchMyLocation}>
                내 주변 순위 보기
              </button>
            )}
          </footer>
        </section>

        <MapControls
          className={styles.controls}
          onZoomIn={() => mapRef.current?.zoomIn()}
          onZoomOut={() => mapRef.current?.zoomOut()}
          onLocate={location ? () => mapRef.current?.panTo(location) : undefined}
        />
        <MapLegend className={styles.legend} title="안전도" items={SAFETY_LEGEND} />
      </div>

      <MapContextMenu
        menu={menu.menu}
        onClose={menu.close}
        items={[
          {
            label: "이 위치 주변 안전구역 검색",
            onSelect: (place) => {
              setQuery(place.label);
              void searchAt(place);
            },
          },
          { label: "여기로 길찾기", onSelect: (place) => router.push(`/route?${placeQuery("end", place)}`) },
        ]}
      />
    </main>
  );
}
