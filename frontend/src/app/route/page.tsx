"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { clearRouteHistory, getRouteHistory, routeSafety, setRouteHistoryRemember, type RouteHistorySnapshot, type RouteResult } from "@/lib/api";
import type { LatLng } from "@/lib/kakao";
import { placeFromQuery, placeQuery, resolvePlace, type Place } from "@/lib/place";
import { addRecent, loadSettings, routeTimeFor } from "@/lib/preferences";
import { saveHandoff } from "@/lib/guideHandoff";
import { formatDistance, guideOptions, walkingMinutes, zoneSummary, type GuideOption } from "@/lib/routeGuidance";
import { useMyLocation } from "@/lib/useMyLocation";
import { useRouteBells } from "@/lib/useRouteBells";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import { AppHeader } from "@/components/AppHeader";
import { AdaptiveBottomSheet } from "@/components/AdaptiveBottomSheet";
import { RoutePeek, type RoutePeekItem } from "@/components/RoutePeek";
import { SafetyMap, type MapLabel, type SafetyMapHandle } from "@/components/SafetyMap";
import {
  MapContextMenu,
  MapControls,
  MapLegend,
  PickConfirm,
  type LegendItem,
  useMapContextMenu,
  usePendingPick,
} from "@/components/MapOverlays";
import { withSearch } from "@/components/WithSearch";
import { AlertIcon, InfoIcon, MapPinIcon, NavigationIcon, SwapIcon } from "@/components/icons";
import styles from "./route.module.css";
import type { SheetSnap } from "@/lib/bottomSheet";

type Field = "start" | "end";

// 경로 칩 + 안내 시작 버튼이 접힌 시트 안에 들어가는 높이(손잡이 44 + 칩 약 87 + 버튼 44 + 여백, 실측 기준).
const PEEK_SHEET_HEIGHT = 204;

// 고른 경로는 초록 실선, 비교하는 다른 경로는 회색 점선.
function routeLegend(compareSelected: boolean, compareName: string): LegendItem[] {
  const [solid, dashed] = compareSelected ? [compareName, "추천 안전 경로"] : ["추천 안전 경로", compareName];
  return [
    { label: solid, swatch: "line", color: "#2e7d32" },
    { label: `${dashed} (비교용)`, swatch: "dash", color: "#9aa0a6" },
    { label: "안전비상벨", swatch: "dot", color: "#f9a825" },
  ];
}

function scoreTone(score: number): string {
  if (score >= 70) return styles.scoreSafe;
  if (score >= 40) return styles.scoreCaution;
  return styles.scoreWarning;
}

export default withSearch(RoutePage);

function RoutePage({ search }: { search: string }) {
  const router = useRouter();
  const user = useSessionUser();
  const { location, request: requestLocation } = useMyLocation();
  const mapRef = useRef<SafetyMapHandle>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const menu = useMapContextMenu();
  const [settings] = useState(loadSettings);
  const [places, setPlaces] = useState<Record<Field, Place | null>>(() => ({
    start: placeFromQuery(search, "start"),
    end: placeFromQuery(search, "end"),
  }));
  const [texts, setTexts] = useState<Record<Field, string>>(() => ({
    start: places.start?.label ?? "",
    end: places.end?.label ?? "",
  }));
  const [picking, setPicking] = useState<Field | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  // 추천 안전 경로(대안 번호) 또는 최단 경로 중 지금 보고 있는 것.
  const [selected, setSelected] = useState<number | "shortest">(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheetSnap, setSheetSnap] = useState<SheetSnap>("collapsed");
  const [searchExpanded, setSearchExpanded] = useState(true);
  const [mobileEditing, setMobileEditing] = useState<Field | null>(null);
  const [history, setHistory] = useState<RouteHistorySnapshot | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const mapPick = usePendingPick();

  useEffect(() => { void getRouteHistory().then(setHistory).catch(() => setHistory(null)); }, []);

  const shortestOption = useMemo(() => (route ? guideOptions(route).find((o) => o.kind === "shortest") : undefined), [route]);
  const activeAlt = typeof selected === "number" ? (route?.alternatives[selected] ?? route?.alternatives[0]) : undefined;
  const activeOption: GuideOption | undefined =
    selected === "shortest"
      ? shortestOption
      : activeAlt && { kind: "safe", points: activeAlt.route_points, zones: activeAlt.zones_passed, distanceM: activeAlt.distance_m };
  const activePoints = activeOption?.points;
  // 지도에는 고른 경로를 실선으로, 비교할 다른 경로(최단 ↔ 추천 안전)를 점선으로 그린다.
  const comparePoints = selected === "shortest" ? route?.alternatives[0]?.route_points : shortestOption?.points;
  const routeBells = useRouteBells(settings.showBells ? activePoints : undefined);
  const shortestM = shortestOption?.distanceM ?? null;
  const shortestSummary = shortestOption ? zoneSummary(shortestOption.zones) : null;
  // 비교 경로는 Tmap 도보 길찾기 결과라 안전 경로보다 길 때도 있다 — 실제로 짧을 때만 "최단"이라 부른다.
  const safeM = route?.alternatives[0]?.distance_m;
  const compareName = shortestM !== null && (safeM === undefined || shortestM < safeM) ? "최단 경로" : "일반 도보 경로";
  // 접힌 시트의 경로 칩: 추천·대안·비교(최단) 경로를 시간·거리·점수만으로 한 줄에 보여준다.
  const peekItems: RoutePeekItem[] = route
    ? [
        ...route.alternatives.map((alt, i) => ({
          key: String(i),
          label: i === 0 ? "추천" : `대안 ${i}`,
          minutes: walkingMinutes(alt.distance_m),
          distance: formatDistance(alt.distance_m),
          score: `${alt.safety_score.toFixed(0)}점`,
          active: alt === activeAlt,
        })),
        ...(shortestOption && shortestM !== null
          ? [
              {
                key: "shortest",
                label: compareName,
                minutes: walkingMinutes(shortestM),
                distance: formatDistance(shortestM),
                score: shortestSummary?.average != null ? `평균 ${shortestSummary.average.toFixed(0)}점` : undefined,
                active: selected === "shortest",
              },
            ]
          : []),
      ]
    : [];
  const pendingPick = picking ? mapPick.pending : null;
  const labels = useMemo<MapLabel[]>(() => {
    const points = activePoints;
    const start = points?.[0] ?? places.start;
    const end = points?.at(-1) ?? places.end;
    return [
      ...(start ? [{ position: start, text: "출발", tone: "start" as const }] : []),
      ...(end ? [{ position: end, text: "도착", tone: "end" as const }] : []),
      ...(pendingPick ? [{ position: pendingPick, text: "선택한 위치", tone: picking === "start" ? ("start" as const) : ("end" as const) }] : []),
    ];
  }, [activePoints, places, pendingPick, picking]);

  function setPlace(field: Field, place: Place) {
    setPlaces((p) => ({ ...p, [field]: place }));
    setTexts((t) => ({ ...t, [field]: place.label }));
    setSearchExpanded(true);
  }

  function editText(field: Field, value: string) {
    setTexts((t) => ({ ...t, [field]: value }));
    setPlaces((p) => ({ ...p, [field]: null }));
  }

  async function confirmMobileEdit() {
    if (!mobileEditing) return;
    const place = places[mobileEditing] ?? await resolvePlace(texts[mobileEditing]);
    if (!place) { setError("주소를 찾을 수 없어요. 정확한 주소를 입력하거나 지도에서 선택해주세요"); return; }
    setPlace(mobileEditing, place);
    setMobileEditing(null);
  }

  function swap() {
    setPlaces((p) => ({ start: p.end, end: p.start }));
    setTexts((t) => ({ start: t.end, end: t.start }));
  }

  function setStartToCurrentLocation() {
    if (!location) {
      requestLocation();
      setError("내 위치를 가져오지 못했어요. 브라우저의 위치 권한을 허용해주세요");
      return;
    }
    setPlace("start", { ...location, label: "현재 위치" });
  }

  function handleMapPick(latlng: LatLng) {
    if (picking) void mapPick.pick(latlng);
  }

  function togglePicking(field: Field) {
    mapPick.clear();
    setPicking((p) => (p === field ? null : field));
  }

  function confirmPick(place: Place) {
    const field = picking;
    if (field) setPlace(field, place);
    setPicking(null);
    mapPick.clear();
    if (field) setMobileEditing(field);
  }

  async function handleSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const [start, end] = await Promise.all([
      places.start ?? resolvePlace(texts.start),
      places.end ?? resolvePlace(texts.end),
    ]);
    if (!start || !end) {
      setError("출발지/도착지 주소를 찾을 수 없어요. 정확한 주소를 입력하거나 지도에서 선택해주세요");
      return;
    }
    setPlaces({ start, end });
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const result = await routeSafety(start.lat, start.lng, end.lat, end.lng, {
        signal: controller.signal,
        at: routeTimeFor(settings.timeMode),
      });
      if (requestRef.current !== controller) return;
      addRecent("destinations", end);
      setRoute(result);
      setSelected(0);
      setSearchExpanded(false);
      // 지도앱처럼 시트는 접어 두고(경로 칩만 보임) 지도를 넓게 보여준다 — 자세한 카드는 시트를 펼치면 나온다.
      setSheetSnap("collapsed");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "경로를 찾지 못했어요");
    } finally {
      if (requestRef.current === controller) setLoading(false);
    }
  }

  function startGuidance(option: GuideOption) {
    const end = option.points.at(-1);
    if (!end) return;
    // 여기서 고른 경로 그대로 안내하도록 넘기고, 길안내의 경로 선택 단계는 건너뛴다.
    const endPlace = { lat: end.lat, lng: end.lng, label: places.end?.label ?? texts.end };
    saveHandoff(endPlace, option);
    router.push(`/navigate?${placeQuery("end", endPlace)}&mode=${option.kind}`);
  }

  if (!user) return null;

  const fields: { key: Field; placeholder: string; dot: string }[] = [
    { key: "start", placeholder: "출발지 주소", dot: styles.dotStart },
    { key: "end", placeholder: "도착지 주소", dot: styles.dotEnd },
  ];

  return (
    <main className={styles.page}>
      <AppHeader userInitial={userInitial(user)} />

      <section className={`${styles.mobileFlow} ${route || picking ? styles.mobileFlowHidden : ""}`} aria-label="길찾기">
        {mobileEditing ? (
          <div className={styles.mobileEditor}>
            <button type="button" className={styles.mobileBack} onClick={() => setMobileEditing(null)}>← 취소</button>
            <h1>{mobileEditing === "start" ? "출발지 입력" : "도착지 입력"}</h1>
            <input autoFocus className={styles.mobileInput} value={texts[mobileEditing]} onChange={(e) => editText(mobileEditing, e.target.value)} placeholder="주소 또는 장소를 입력하세요" />
            <div className={styles.mobileActions}>
              {mobileEditing === "start" && <button type="button" onClick={setStartToCurrentLocation}>현재 위치</button>}
              <button type="button" onClick={() => { setPicking(mobileEditing); setMobileEditing(null); }}>지도에서 선택</button>
            </div>
            <button type="button" className={styles.primaryButton} onClick={() => void confirmMobileEdit()}>확인</button>
          </div>
        ) : (
          <div className={styles.mobileIdle}>
            <h1>길찾기</h1>
            {fields.map(({ key, placeholder }) => <button key={key} type="button" className={styles.mobilePlaceRow} onClick={() => setMobileEditing(key)}><span>{places[key]?.label ?? placeholder}</span><b>확인</b></button>)}
            <button type="button" className={styles.primaryButton} disabled={!places.start || !places.end || loading} onClick={() => void handleSearch({ preventDefault: () => undefined } as React.FormEvent<HTMLFormElement>)}>{loading ? "경로 찾는 중..." : "경로 검색"}</button>
            <div className={styles.historyControls}>
              <label><input type="checkbox" checked={history?.rememberRouteHistory ?? true} onChange={(e) => void setRouteHistoryRemember(e.target.checked).then(setHistory)} /> 경로 기억</label>
              <button type="button" onClick={() => { if (window.confirm("최근 경로를 모두 삭제할까요?")) void clearRouteHistory().then(() => setHistory((value) => value ? { ...value, items: [] } : value)); }}>전체 기록 삭제</button>
            </div>
            {history?.items.map((item) => <button key={`${item.start.lat}-${item.end.lat}`} type="button" className={styles.historyItem} onClick={() => { setPlace("start", item.start); setPlace("end", item.end); }}>{item.start.label} → {item.end.label}</button>)}
          </div>
        )}
      </section>

      <div ref={layoutRef} className={styles.layout} data-sheet-snap={sheetSnap} data-has-route={Boolean(route || picking)} data-picking={picking ?? undefined}>
        <aside className={styles.sidebar}>
          {route && !searchExpanded ? (
            <button type="button" className={styles.compactSearch} onClick={() => setSearchExpanded(true)}>
              <span><small>출발</small>{places.start?.label ?? texts.start}</span>
              <SwapIcon size={16} />
              <span><small>도착</small>{places.end?.label ?? texts.end}</span>
            </button>
          ) : (
            <div className={styles.searchPanel}>
              <div className={styles.sidebarHeader}>
                <h1 className={styles.title}>길찾기</h1>
                <button type="button" className={styles.linkButton} onClick={setStartToCurrentLocation}>
                  현재 위치를 출발지로
                </button>
              </div>

              <form onSubmit={handleSearch} className={styles.form}>
                <div className={styles.fields}>
                  {fields.map(({ key, placeholder, dot }) => (
                    <div key={key} className={styles.field}>
                      <span className={`${styles.dot} ${dot}`} aria-hidden />
                      <input
                        className={styles.input}
                        value={texts[key]}
                        onChange={(e) => editText(key, e.target.value)}
                        placeholder={placeholder}
                        aria-label={placeholder}
                        required
                      />
                      <button
                        type="button"
                        className={`${styles.pickButton} ${picking === key ? styles.pickButtonActive : ""}`}
                        onClick={() => togglePicking(key)}
                        aria-label={`${key === "start" ? "출발지" : "도착지"}를 지도에서 선택`}
                        aria-pressed={picking === key}
                      >
                        <MapPinIcon size={16} />
                      </button>
                    </div>
                  ))}
                  <button type="button" className={styles.swapButton} onClick={swap} aria-label="출발지와 도착지 바꾸기">
                    <SwapIcon size={16} />
                  </button>
                </div>
                <button type="submit" className={styles.primaryButton} disabled={loading}>
                  {loading ? "경로 찾는 중..." : "안전 경로 찾기"}
                </button>
              </form>

              {route && (
                <button type="button" className={styles.collapseSearch} onClick={() => setSearchExpanded(false)}>
                  검색 조건 접기
                </button>
              )}
              {picking && (
                <p className={styles.hint}>지도를 클릭해서 {picking === "start" ? "출발지" : "도착지"}를 선택하세요</p>
              )}
              {error && (
                <p className={styles.error} role="alert">
                  <AlertIcon size={16} />
                  {error}
                </p>
              )}
            </div>
          )}

          <AdaptiveBottomSheet
            className={styles.resultsSheet}
            label="경로 결과"
            snap={sheetSnap}
            onSnapChange={setSheetSnap}
            workspaceRef={layoutRef}
            collapsedHeight={route ? PEEK_SHEET_HEIGHT : undefined}
            summary={route && activeOption ? (
              <RoutePeek
                items={peekItems}
                onSelect={(key) => setSelected(key === "shortest" ? "shortest" : Number(key))}
                onStart={() => startGuidance(activeOption)}
              />
            ) : (
              <div className={styles.sheetSummary}><strong>경로 검색</strong><span>출발지와 도착지를 입력하세요</span></div>
            )}
          >
          {route ? (
            <section className={styles.results} aria-label="경로 검색 결과">
              <p className={styles.resultsLabel}>
                검색 결과 {route.alternatives.length}개
                <span className={`${styles.periodBadge} ${route.period === "night" ? styles.periodNight : ""}`}>
                  {route.period === "night" ? "야간 기준" : "주간 기준"}
                </span>
              </p>
              {route.mode !== "safety_weighted" && (
                <p className={styles.fallback}>
                  <InfoIcon size={14} />
                  {route.mode === "tmap"
                    ? "안전 경로를 찾지 못해 일반 도보 경로로 안내해요"
                    : "도보 경로를 가져오지 못해 직선 거리로 추정했어요"}
                </p>
              )}

              {route.alternatives.map((alt, i) => {
                const active = alt === activeAlt;
                const passed = alt.zones_passed.slice(0, 3).map((z) => z.dong_name).join(", ");
                const extraM = shortestM === null ? null : alt.distance_m - shortestM;
                return (
                  <article
                    key={`${alt.distance_m}-${i}`}
                    className={`${styles.routeCard} ${active ? styles.routeCardActive : ""}`}
                  >
                    <button type="button" className={styles.routeCardMain} onClick={() => setSelected(i)}>
                      <span className={`${styles.tag} ${i === 0 ? styles.tagBest : ""}`}>
                        {i === 0 ? "추천: 가장 안전" : `대안 ${i}`}
                      </span>
                      <span className={styles.routeTime}>
                        {walkingMinutes(alt.distance_m)}분 <small>{formatDistance(alt.distance_m)}</small>
                      </span>
                      <span className={styles.routeMeta}>
                        <span className={`${styles.scoreBadge} ${scoreTone(alt.safety_score)}`}>
                          안전지수 {alt.safety_score.toFixed(0)}점
                        </span>
                        {passed && <span className={styles.passed}>지나가는 동: {passed}</span>}
                      </span>
                    </button>
                    {active && (
                      <div className={styles.routeCardDetail}>
                        {extraM !== null && (
                          <p className={styles.note}>
                            <InfoIcon size={14} />
                            {extraM > 20
                              ? `${compareName}보다 ${formatDistance(extraM)} 더 걷는 대신 안전도를 반영해 고른 길이에요`
                              : extraM < -20
                                ? `${compareName}보다 ${formatDistance(-extraM)} 짧으면서 안전도도 반영한 길이에요`
                                : `${compareName}와 거의 같은 거리예요`}
                          </p>
                        )}
                        <button
                          type="button"
                          className={styles.primaryButton}
                          onClick={() => activeOption && startGuidance(activeOption)}
                        >
                          <NavigationIcon size={16} />
                          실시간 안내 시작
                        </button>
                      </div>
                    )}
                  </article>
                );
              })}

              {shortestOption && shortestM !== null && (
                <article
                  className={`${styles.routeCard} ${selected === "shortest" ? styles.routeCardActive : ""}`}
                >
                  <button type="button" className={styles.routeCardMain} onClick={() => setSelected("shortest")}>
                    <span className={styles.tag}>{compareName}</span>
                    <span className={styles.routeTime}>
                      {walkingMinutes(shortestM)}분 <small>{formatDistance(shortestM)}</small>
                    </span>
                    <span className={styles.routeMeta}>
                      {shortestSummary?.average != null && (
                        <span className={`${styles.scoreBadge} ${scoreTone(shortestSummary.average)}`}>
                          지나는 동 평균 {shortestSummary.average.toFixed(0)}점
                        </span>
                      )}
                      <span className={styles.passed}>
                        {shortestSummary && shortestSummary.cautionCount > 0
                          ? `주의 구역 ${shortestSummary.cautionCount}곳`
                          : "주의 구역 없음"}
                      </span>
                    </span>
                  </button>
                  {selected === "shortest" && (
                    <div className={styles.routeCardDetail}>
                      <p className={styles.note}>
                        <InfoIcon size={14} />
                        {compareName === "최단 경로"
                          ? "안전도를 반영하지 않고 가장 짧게 걷는 길이에요"
                          : "안전도를 반영하지 않은 일반 도보 길찾기 경로예요"}
                      </p>
                      <button
                        type="button"
                        className={styles.primaryButton}
                        onClick={() => startGuidance(shortestOption)}
                      >
                        <NavigationIcon size={16} />
                        실시간 안내 시작
                      </button>
                    </div>
                  )}
                </article>
              )}
            </section>
          ) : (
            <p className={styles.empty}>출발지와 도착지를 입력하거나, 지도를 우클릭해서 선택해보세요.</p>
          )}
            <MapLegend
              className={styles.mobileLegend}
              title="지도 범례"
              items={routeLegend(selected === "shortest", compareName)}
            />
          </AdaptiveBottomSheet>
        </aside>

        <div className={styles.mapArea}>
          <SafetyMap
            ref={mapRef}
            bells={routeBells}
            center={location ?? undefined}
            myLocation={location ?? undefined}
            routePath={activePoints}
            comparePath={comparePoints}
            labels={labels}
            onSelect={handleMapPick}
            onContextMenu={menu.open}
            height="100%"
          />
          <MapLegend
            className={styles.legend}
            title="지도 범례"
            items={routeLegend(selected === "shortest", compareName)}
          />
          <MapControls
            className={styles.controls}
            onZoomIn={() => mapRef.current?.zoomIn()}
            onZoomOut={() => mapRef.current?.zoomOut()}
            onLocate={location ? () => mapRef.current?.panTo(location) : undefined}
          />
          <PickConfirm
            className={styles.pickConfirm}
            pending={pendingPick}
            title={picking ? "경로" : undefined}
            confirmLabel={picking === "start" ? "출발지로 설정" : "도착지로 설정"}
            onConfirm={confirmPick}
            onCancel={mapPick.clear}
          />
        </div>
      </div>

      <MapContextMenu
        menu={menu.menu}
        onClose={menu.close}
        items={[
          { label: "출발지로 설정", onSelect: (place) => setPlace("start", place) },
          { label: "도착지로 설정", onSelect: (place) => setPlace("end", place) },
          { label: "이 위치 주변 안전구역 검색", onSelect: (place) => router.push(`/?${placeQuery("near", place)}`) },
        ]}
      />
    </main>
  );
}
