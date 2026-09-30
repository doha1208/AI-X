"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { routeSafety, type SafetyZone } from "@/lib/api";
import { haversineMeters } from "@/lib/geo";
import type { LatLng } from "@/lib/kakao";
import { acceptFix, GEO_OPTIONS, toFix, type Fix } from "@/lib/locationFilter";
import { loadHandoff } from "@/lib/guideHandoff";
import { placeFromQuery, placeQuery, resolvePlace, type Place } from "@/lib/place";
import { loadRecent, loadSettings, routeTimeFor, saveSettings, type Settings } from "@/lib/preferences";
import {
  formatDistance,
  guideOptions,
  nextTurn,
  progressAlong,
  walkingMinutes,
  zoneSummary,
  type GuideKind,
  type GuideOption,
  type TurnDirection,
} from "@/lib/routeGuidance";
import { useMyLocation } from "@/lib/useMyLocation";
import { useRouteBells } from "@/lib/useRouteBells";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import { AppHeader } from "@/components/AppHeader";
import { AdaptiveBottomSheet } from "@/components/AdaptiveBottomSheet";
import { SafetyMap, type MapLabel, type SafetyMapHandle } from "@/components/SafetyMap";
import { MapControls, PickConfirm, usePendingPick } from "@/components/MapOverlays";
import { withSearch } from "@/components/WithSearch";
import {
  AlertIcon,
  CloseIcon,
  LocateIcon,
  MapPinIcon,
  NavigationIcon,
  PhoneIcon,
  SearchIcon,
  ShareIcon,
  SpeakerIcon,
  SpeakerOffIcon,
  TurnRightIcon,
} from "@/components/icons";
import styles from "./navigate.module.css";
import type { SheetSnap } from "@/lib/bottomSheet";

const ARRIVAL_RADIUS_M = 30;
// 가장 가까운 경로 지점에서 이보다 멀어지면 경로를 벗어난 것으로 보고 다시 찾는다.
const OFF_ROUTE_M = 40;
const REROUTE_MIN_INTERVAL_MS = 5000;
const TOAST_MS = 2500;

const TURN_TEXT: Record<TurnDirection, string> = { left: "좌회전", right: "우회전", arrive: "앞 목적지" };

function scoreLevel(score: number): { label: string; tone: string } {
  if (score >= 70) return { label: "안전", tone: styles.toneSafe };
  if (score >= 40) return { label: "보통", tone: styles.toneCaution };
  return { label: "주의", tone: styles.toneWarning };
}

function nearestZone(zones: SafetyZone[], here: LatLng): SafetyZone | null {
  return zones.reduce<SafetyZone | null>(
    (best, z) => (!best || haversineMeters(here, z) < haversineMeters(here, best) ? z : best),
    null
  );
}

function speak(text: string, volume: number) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "ko-KR";
  utterance.volume = volume;
  window.speechSynthesis.speak(utterance);
}

export default withSearch(NavigatePage);

function NavigatePage({ search }: { search: string }) {
  const user = useSessionUser();
  const { location, denied: locationDenied } = useMyLocation();
  const mapRef = useRef<SafetyMapHandle>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [settings, setSettings] = useState(loadSettings);
  const [voicePanelOpen, setVoicePanelOpen] = useState(false);
  const [sheetSnap, setSheetSnap] = useState<SheetSnap>("collapsed");
  const [recent] = useState(() => loadRecent("destinations"));
  const [destination, setDestination] = useState<Place | null>(() =>
    placeFromQuery(search, "end")
  );
  const [position, setPosition] = useState<LatLng | null>(null);
  // 목적지를 정하면 먼저 안전 경로·최단 경로를 보여주고(choice), 고른 경로(mode)로 안내한다(guided).
  // 길찾기 탭에서 이미 경로를 골라 넘어온 경우(?mode=safe|shortest)에는 고르는 단계를 건너뛴다.
  const [choice, setChoice] = useState<{ options: GuideOption[]; safetyWeighted: boolean } | null>(null);
  const [mode, setMode] = useState<GuideKind | null>(() => {
    const requested = new URLSearchParams(search).get("mode");
    return requested === "safe" || requested === "shortest" ? requested : null;
  });
  // 길찾기 탭에서 고른 경로가 넘어왔으면 새로 찾지 않고 그 경로 그대로 안내한다.
  const [guided, setGuided] = useState<GuideOption | null>(() => {
    const end = placeFromQuery(search, "end");
    return end && typeof window !== "undefined" ? loadHandoff(end) : null;
  });
  const [previewKind, setPreviewKind] = useState<GuideKind>("safe");
  const [denied, setDenied] = useState(false);
  const [arrived, setArrived] = useState(false);
  const [rerouting, setRerouting] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [watchKey, setWatchKey] = useState(0);
  const [query, setQuery] = useState("");
  const [picking, setPicking] = useState(false);
  const [chooseError, setChooseError] = useState<string | null>(null);
  const inFlightRef = useRef(false);
  const lastFetchAtRef = useRef(0);
  const handlerRef = useRef<(pos: GeolocationPosition) => void>(() => {});
  const lastFixRef = useRef<Fix | null>(null);
  const mapPick = usePendingPick();

  const routeBells = useRouteBells(settings.showBells ? guided?.points : undefined);
  const pendingPick = picking ? mapPick.pending : null;
  const labels = useMemo<MapLabel[]>(() => {
    if (destination) return [{ position: destination, text: "목적지", tone: "end" }];
    return pendingPick ? [{ position: pendingPick, text: "선택한 위치", tone: "end" }] : [];
  }, [destination, pendingPick]);
  const guidance = useMemo(() => {
    if (!guided || !position || guided.points.length < 2) return null;
    const progress = progressAlong(guided.points, position);
    return {
      progress,
      turn: nextTurn(guided.points, position, progress.index),
      zone: nearestZone(guided.zones, position),
    };
  }, [guided, position]);

  // purpose "options": 고를 경로 둘을 가져온다. "guide": 고른 종류로 (재)안내할 경로를 가져온다.
  async function fetchRoute(from: LatLng, to: Place, purpose: "options" | "guide", isReroute: boolean) {
    inFlightRef.current = true;
    lastFetchAtRef.current = Date.now();
    setRerouting(isReroute);
    try {
      const result = await routeSafety(from.lat, from.lng, to.lat, to.lng, {
        includeComparison: purpose === "options" || mode === "shortest",
        at: routeTimeFor(settings.timeMode),
      });
      const found = guideOptions(result);
      if (purpose === "options") {
        setChoice({ options: found, safetyWeighted: result.mode === "safety_weighted" });
        setSheetSnap("half");
      } else {
        const next = found.find((option) => option.kind === mode) ?? found[0];
        if (mode === "shortest" && next.kind !== "shortest") {
          setMode("safe");
          showToast("최단 경로를 가져오지 못해 안전 경로로 안내해요");
        }
        setGuided(next);
      }
      setRouteError(null);
    } catch (err) {
      // 자동 재시도는 멈추고 사용자가 "다시 시도"를 누르게 한다(거리 초과 같은 오류는 반복해도 같다).
      setRouteError(err instanceof Error ? err.message : "경로를 찾지 못했어요");
    } finally {
      inFlightRef.current = false;
      setRerouting(false);
    }
  }

  function handlePosition(pos: GeolocationPosition) {
    // 튄 GPS 값은 버린다 — 받아들이면 내 위치가 엉뚱한 곳으로 튀고 경로 이탈로 오인해 다시 찾게 된다.
    const fix = toFix(pos);
    if (!acceptFix(lastFixRef.current, fix)) return;
    lastFixRef.current = fix;
    const here = { lat: fix.lat, lng: fix.lng };
    setPosition(here);
    setDenied(false);
    if (!destination || arrived || routeError || inFlightRef.current) return;
    if (!mode) {
      if (!choice) void fetchRoute(here, destination, "options", false);
      return;
    }
    if (haversineMeters(here, destination) <= ARRIVAL_RADIUS_M) {
      setArrived(true);
      if (settings.voiceOn) speak("목적지에 도착했어요. 안내를 종료합니다.", settings.voiceVolume);
      return;
    }
    const offRoute = !guided || progressAlong(guided.points, here).offRouteM > OFF_ROUTE_M;
    if (!offRoute) return;
    if (Date.now() - lastFetchAtRef.current < REROUTE_MIN_INTERVAL_MS) return;
    void fetchRoute(here, destination, "guide", guided !== null);
  }

  // watchPosition 콜백이 항상 최신 상태(경로·목적지)를 보도록 최신 핸들러를 ref에 둔다.
  useEffect(() => {
    handlerRef.current = handlePosition;
  });

  useEffect(() => {
    if (!destination || arrived || !navigator.geolocation) return;
    const id = navigator.geolocation.watchPosition(
      (pos) => handlerRef.current(pos),
      (err) => {
        if (err.code === err.PERMISSION_DENIED) setDenied(true);
      },
      GEO_OPTIONS
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [destination, arrived, watchKey]);

  const turnKey = guidance ? `${guidance.turn.vertex}-${guidance.turn.direction}` : null;
  useEffect(() => {
    if (!turnKey || !settings.voiceOn || !guidance) return;
    const { turn } = guidance;
    speak(
      `${formatDistance(turn.distanceM)} ${turn.direction === "arrive" ? "앞에 목적지가 있어요" : `앞에서 ${TURN_TEXT[turn.direction]}하세요`}`,
      settings.voiceVolume
    );
    // 새 회전 지점이 잡힐 때만 말한다 — 거리·음량이 바뀔 때마다 다시 말하지 않도록 의존성을 좁혔다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turnKey, settings.voiceOn]);

  function updateVoice(patch: Partial<Pick<Settings, "voiceOn" | "voiceVolume">>) {
    if (patch.voiceOn === false && "speechSynthesis" in window) window.speechSynthesis.cancel();
    setSettings((current) => {
      const next = { ...current, ...patch };
      saveSettings(next);
      return next;
    });
  }

  function showToast(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), TOAST_MS);
  }

  function clearRoute() {
    setChoice(null);
    setPreviewKind("safe");
    setMode(null);
    setGuided(null);
    setArrived(false);
    setRouteError(null);
  }

  function startTo(place: Place) {
    clearRoute();
    setDestination(place);
    stopPicking();
    setChooseError(null);
    lastFetchAtRef.current = 0;
    window.history.replaceState(null, "", `/navigate?${placeQuery("end", place)}`);
    // 위치가 이미 있으면 다음 GPS 갱신을 기다리지 않고 바로 두 경로를 비교한다.
    const here = position ?? location;
    if (here) void fetchRoute(here, place, "options", false);
  }

  function chooseOption(option: GuideOption) {
    setMode(option.kind);
    setGuided(option);
    setSheetSnap("collapsed");
    lastFetchAtRef.current = Date.now();
  }

  function reset() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    clearRoute();
    setDestination(null);
    setPosition(null);
    window.history.replaceState(null, "", "/navigate");
  }

  function endGuidance() {
    if (window.confirm("안내를 종료할까요?")) reset();
  }

  function retryRoute() {
    setRouteError(null);
    lastFetchAtRef.current = 0;
    if (position && destination) void fetchRoute(position, destination, mode ? "guide" : "options", false);
  }

  async function chooseByText(text: string) {
    const place = await resolvePlace(text);
    if (place) startTo(place);
    else setChooseError("주소를 찾을 수 없어요. 정확한 주소를 입력하거나 지도에서 선택해주세요");
  }

  function handleMapPick(latlng: LatLng) {
    if (picking) void mapPick.pick(latlng);
  }

  function stopPicking() {
    setPicking(false);
    mapPick.clear();
  }

  async function shareLocation() {
    const here = position ?? location;
    if (!here) return;
    const url = `https://map.kakao.com/link/map/${encodeURIComponent("내 현재 위치")},${here.lat},${here.lng}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: "내 현재 위치", url });
      } else {
        await navigator.clipboard.writeText(url);
        showToast("위치 링크를 복사했어요");
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) showToast("위치를 공유하지 못했어요");
    }
  }

  if (!user) return null;

  const myLocation = position ?? location ?? undefined;
  const phase = !destination ? "choose" : denied ? "denied" : arrived ? "arrived" : mode ? "guiding" : "select";
  const safeOption = choice?.options.find((o) => o.kind === "safe");
  // 카드를 누르면 그 경로만 지도에서 강조하고(실선), 나머지는 비교용 점선으로 둔다.
  const previewOption = choice?.options.find((o) => o.kind === previewKind) ?? choice?.options[0];
  const otherOption = choice?.options.find((o) => o !== previewOption);
  const remainingM = guidance?.progress.remainingM ?? 0;
  const progressPct = guidance
    ? Math.min(100, Math.max(0, Math.round((1 - guidance.progress.remainingM / Math.max(1, guidance.progress.totalM)) * 100)))
    : 0;
  const zoneLevel = guidance?.zone ? scoreLevel(guidance.zone.safety_score) : null;

  return (
    <main className={styles.page}>
      <AppHeader userInitial={userInitial(user)} />

      <div ref={stageRef} className={styles.stage}>
        <SafetyMap
          ref={mapRef}
          bells={phase === "guiding" ? routeBells : undefined}
          center={myLocation}
          myLocation={myLocation}
          routePath={phase === "guiding" ? guided?.points : phase === "select" ? previewOption?.points : undefined}
          comparePath={phase === "select" ? otherOption?.points : undefined}
          labels={labels}
          followLocation={phase === "guiding"}
          onSelect={handleMapPick}
          height="100%"
        />

        {phase === "guiding" && (
          <>
            <section className={styles.turnCard}>
              {routeError ? (
                <>
                  <span className={`${styles.turnIcon} ${styles.turnIconError}`}>
                    <AlertIcon size={24} />
                  </span>
                  <div className={styles.turnText} aria-live="polite">
                    <p className={styles.turnTitle}>경로를 찾지 못했어요</p>
                    <p className={styles.turnSub}>{routeError}</p>
                  </div>
                  <button type="button" className={styles.retryButton} onClick={retryRoute}>
                    다시 시도
                  </button>
                </>
              ) : guidance ? (
                <>
                  <span className={styles.turnIcon}>
                    {guidance.turn.direction === "arrive" ? (
                      <MapPinIcon size={26} />
                    ) : (
                      <TurnRightIcon size={26} className={guidance.turn.direction === "left" ? styles.mirror : undefined} />
                    )}
                  </span>
                  <div className={styles.turnText} aria-live="polite">
                    <p className={styles.turnTitle}>
                      {formatDistance(guidance.turn.distanceM)}{" "}
                      <span className={styles.turnAction}>{TURN_TEXT[guidance.turn.direction]}</span>
                    </p>
                    <p className={styles.turnSub}>목적지 · {destination?.label}</p>
                  </div>
                  <button
                    type="button"
                    className={`${styles.soundButton} ${voicePanelOpen ? styles.soundButtonOpen : ""}`}
                    onClick={() => setVoicePanelOpen((open) => !open)}
                    aria-label="음성 안내 설정"
                    aria-expanded={voicePanelOpen}
                  >
                    {settings.voiceOn && settings.voiceVolume > 0 ? <SpeakerIcon size={20} /> : <SpeakerOffIcon size={20} />}
                  </button>
                  {voicePanelOpen && (
                    <div className={styles.voicePanel}>
                      <div className={styles.voiceRow}>
                        <span className={styles.voiceTitle} id="voice-toggle">
                          음성 안내
                        </span>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={settings.voiceOn}
                          aria-labelledby="voice-toggle"
                          className={`${styles.switch} ${settings.voiceOn ? styles.switchOn : ""}`}
                          onClick={() => updateVoice({ voiceOn: !settings.voiceOn })}
                        >
                          <span className={styles.switchKnob} />
                        </button>
                      </div>
                      <div className={styles.volumeRow}>
                        <SpeakerOffIcon size={16} />
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={10}
                          value={Math.round(settings.voiceVolume * 100)}
                          onChange={(e) => updateVoice({ voiceVolume: Number(e.target.value) / 100 })}
                          disabled={!settings.voiceOn}
                          aria-label="음량"
                          className={styles.volumeSlider}
                        />
                        <SpeakerIcon size={16} />
                        <span className={styles.volumeValue}>{Math.round(settings.voiceVolume * 100)}%</span>
                      </div>
                      <button
                        type="button"
                        className={styles.previewButton}
                        onClick={() => speak("안내 음성은 이 크기로 들려요", settings.voiceVolume)}
                        disabled={!settings.voiceOn || settings.voiceVolume === 0}
                      >
                        미리 듣기
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <span className={styles.turnIcon}>
                    <NavigationIcon size={24} />
                  </span>
                  <div className={styles.turnText} aria-live="polite">
                    <p className={styles.turnTitle}>{position ? "안전 경로를 찾는 중..." : "현재 위치를 찾는 중..."}</p>
                    <p className={styles.turnSub}>목적지 · {destination?.label}</p>
                  </div>
                </>
              )}
            </section>

            {rerouting && <p className={styles.rerouting}>경로를 벗어나 다시 찾는 중...</p>}

            {guidance?.zone && zoneLevel && (
              <section className={styles.zoneCard} aria-label="현재 구간 안전도">
                <p className={styles.zoneLabel}>현재 구간 안전도</p>
                <p className={`${styles.zoneScore} ${zoneLevel.tone}`}>
                  {guidance.zone.safety_score.toFixed(0)}
                  <small>점</small>
                </p>
                <p className={styles.zoneName}>
                  {guidance.zone.dong_name} · <span className={zoneLevel.tone}>{zoneLevel.label}</span>
                </p>
                <div className={styles.meter}>
                  <span className={`${styles.meterFill} ${zoneLevel.tone}`} style={{ width: `${guidance.zone.safety_score}%` }} />
                </div>
              </section>
            )}

            <AdaptiveBottomSheet
              className={styles.bottomPanel}
              label="길안내 정보"
              snap={sheetSnap}
              onSnapChange={setSheetSnap}
              workspaceRef={stageRef}
              summary={(
                <div className={`${styles.stats} ${styles.mobileStats}`}>
                  <div>
                    <p className={styles.statLabel}>남은 시간</p>
                    <p className={styles.statValue}>{guidance ? walkingMinutes(remainingM) : "-"}<small>분</small></p>
                  </div>
                  <div className={styles.statDivider} />
                  <div>
                    <p className={styles.statLabel}>거리</p>
                    <p className={styles.statValue}>{guidance ? formatDistance(remainingM) : "-"}</p>
                  </div>
                </div>
              )}
            >
              <div className={styles.bottomPanelContent}>
              <div className={`${styles.stats} ${styles.desktopStats}`}>
                <div>
                  <p className={styles.statLabel}>남은 시간</p>
                  <p className={styles.statValue}>
                    {guidance ? walkingMinutes(remainingM) : "-"}
                    <small>분</small>
                  </p>
                </div>
                <div className={styles.statDivider} />
                <div>
                  <p className={styles.statLabel}>거리</p>
                  <p className={styles.statValue}>{guidance ? formatDistance(remainingM) : "-"}</p>
                </div>
                <button type="button" className={styles.endButton} onClick={endGuidance}>
                  <CloseIcon size={16} />
                  안내 종료
                </button>
              </div>
              <div className={styles.progressLabels}>
                <span className={zoneLevel?.tone}>{zoneLevel ? `${zoneLevel.label} 구역 통과 중` : "안내 준비 중"}</span>
                <span>{progressPct}% 이동</span>
              </div>
              <div className={styles.progress}>
                <span className={styles.progressFill} style={{ width: `${progressPct}%` }} />
              </div>
              {guidance?.zone && zoneLevel && (
                <div className={styles.mobileZoneDetail} aria-label="현재 구간 안전 안내">
                  <span>현재 구간</span>
                  <strong className={zoneLevel.tone}>{guidance.zone.dong_name} · {guidance.zone.safety_score.toFixed(0)}점</strong>
                  <span className={zoneLevel.tone}>{zoneLevel.label} 구역을 통과하고 있어요</span>
                </div>
              )}
              <div className={styles.mobileGuidanceActions}>
                <button type="button" className={styles.endButton} onClick={endGuidance}>
                  <CloseIcon size={16} />
                  안내 종료
                </button>
              </div>
              </div>
            </AdaptiveBottomSheet>
          </>
        )}

        {phase === "select" && (
          <AdaptiveBottomSheet
            className={styles.choicePanel}
            label="안내 경로 선택"
            snap={sheetSnap}
            onSnapChange={setSheetSnap}
            workspaceRef={stageRef}
            summary={(
              <div className={styles.choiceSummary}>
                <span>목적지 · {destination?.label}</span>
                <strong>{previewOption ? `${walkingMinutes(previewOption.distanceM)}분 · ${formatDistance(previewOption.distanceM)}` : "경로 찾는 중"}</strong>
              </div>
            )}
          >
          <div className={styles.choicePanelContent}>
            <div className={styles.choiceHeader}>
              <div>
                <h1 className={styles.choiceTitle}>어떤 길로 안내할까요?</h1>
                <p className={styles.choiceSub}>목적지 · {destination?.label}</p>
              </div>
              <button type="button" className={styles.ghostButton} onClick={reset}>
                취소
              </button>
            </div>

            {routeError ? (
              <div className={styles.choiceStatus} role="alert">
                <p className={styles.error}>경로를 찾지 못했어요: {routeError}</p>
                <button type="button" className={styles.startButton} onClick={retryRoute}>
                  다시 시도
                </button>
              </div>
            ) : !choice ? (
              <p className={styles.choiceStatus} role="status">
                {myLocation ? "안전 경로와 최단 경로를 비교하는 중..." : "현재 위치를 찾는 중..."}
              </p>
            ) : (
              <>
                <div className={styles.choiceList}>
                  {choice.options.map((option) => {
                    const summary = zoneSummary(option.zones);
                    const isSafe = option.kind === "safe";
                    // 비교 경로는 Tmap 도보 길찾기 결과라 안전 경로보다 길 때도 있다 — 실제로 짧을 때만 "최단"이라 부른다.
                    const reallyShortest = !isSafe && (!safeOption || option.distanceM < safeOption.distanceM);
                    const title = isSafe
                      ? choice.safetyWeighted ? "안전 경로" : "도보 경로"
                      : reallyShortest ? "최단 경로" : "일반 도보 경로";
                    const selected = option === previewOption;
                    return (
                      <div
                        key={option.kind}
                        className={`${styles.choiceCard} ${selected ? styles.choiceCardSelected : ""}`}
                      >
                        <button
                          type="button"
                          className={styles.choiceSelect}
                          onClick={() => setPreviewKind(option.kind)}
                          aria-pressed={selected}
                        >
                          <span className={styles.choiceKind}>
                            <span className={selected ? styles.swatchLine : styles.swatchDash} aria-hidden />
                            {title}
                            {isSafe && choice.safetyWeighted && <span className={styles.recommendTag}>추천</span>}
                          </span>
                          <span className={styles.choiceTime}>
                            {walkingMinutes(option.distanceM)}분 <small>{formatDistance(option.distanceM)}</small>
                          </span>
                          <span className={styles.choiceMeta}>
                            {summary.average !== null && (
                              <span className={scoreLevel(summary.average).tone}>
                                지나는 동 평균 {summary.average.toFixed(0)}점
                              </span>
                            )}
                            <span>{summary.cautionCount > 0 ? `주의 구역 ${summary.cautionCount}곳` : "주의 구역 없음"}</span>
                          </span>
                          {!selected && <span className={styles.choiceHint}>눌러서 지도에서 보기</span>}
                        </button>
                        {selected && (
                          <button type="button" className={styles.choiceStart} onClick={() => chooseOption(option)}>
                            이 길로 안내 시작
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
                {!choice.safetyWeighted ? (
                  <p className={styles.choiceNote}>안전 경로를 찾지 못해 일반 도보 경로로만 안내할 수 있어요.</p>
                ) : (
                  choice.options.length === 1 && (
                    <p className={styles.choiceNote}>최단 경로를 가져오지 못해 안전 경로로만 안내할 수 있어요.</p>
                  )
                )}
              </>
            )}
          </div>
          </AdaptiveBottomSheet>
        )}

        {phase === "choose" && picking && (
          <>
            <p className={styles.pickHint} role="status">
              <MapPinIcon size={16} />
              지도를 눌러 도착지를 선택하세요
            </p>
            <button type="button" className={styles.pickCancel} onClick={stopPicking}>
              <CloseIcon size={16} />
              주소로 입력하기
            </button>
            <PickConfirm
              className={styles.pickConfirm}
              pending={mapPick.pending}
              confirmLabel="여기로 안내"
              onConfirm={startTo}
              onCancel={mapPick.clear}
            />
          </>
        )}

        {phase === "choose" && !picking && (
          <section className={styles.centerCard} aria-label="목적지 선택">
            <h1 className={styles.centerTitle}>어디로 안내할까요?</h1>
            <p className={styles.centerSub}>현재 위치에서 출발하는 안전 경로와 최단 경로를 비교해서 고를 수 있어요.</p>
            <form
              className={styles.searchRow}
              onSubmit={(e) => {
                e.preventDefault();
                void chooseByText(query);
              }}
            >
              <SearchIcon size={18} className={styles.searchIcon} />
              <input
                className={styles.searchInput}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="도착지 주소를 입력하세요"
                aria-label="도착지 주소"
                required
              />
              <button type="submit" className={styles.startButton}>
                경로 찾기
              </button>
            </form>
            <button type="button" className={styles.pickChip} onClick={() => setPicking(true)}>
              <MapPinIcon size={14} />
              지도에서 선택
            </button>
            {chooseError && (
              <p className={styles.error} role="alert">
                {chooseError}
              </p>
            )}
            {locationDenied && (
              <p className={styles.error}>위치 권한을 허용해야 실시간 안내를 시작할 수 있어요.</p>
            )}
            {recent.length > 0 && (
              <div className={styles.recent}>
                <p className={styles.recentTitle}>최근 목적지</p>
                <ul className={styles.recentList}>
                  {recent.map((entry) => (
                    <li key={entry.label}>
                      <button type="button" className={styles.recentItem} onClick={() => void chooseByText(entry.label)}>
                        <MapPinIcon size={15} />
                        {entry.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        {phase === "denied" && (
          <section className={styles.centerCard} role="alert">
            <span className={`${styles.stateIcon} ${styles.toneWarning}`}>
              <LocateIcon size={26} />
            </span>
            <h1 className={styles.centerTitle}>위치 권한이 필요해요</h1>
            <p className={styles.centerSub}>
              실시간 안내는 현재 위치를 따라가며 길을 알려줘요. 브라우저 주소창의 위치 권한을 허용한 뒤 다시 시도해주세요.
            </p>
            <div className={styles.centerActions}>
              <button
                type="button"
                className={styles.startButton}
                onClick={() => {
                  setDenied(false);
                  setWatchKey((k) => k + 1);
                }}
              >
                다시 시도
              </button>
              <button type="button" className={styles.ghostButton} onClick={reset}>
                안내 취소
              </button>
            </div>
          </section>
        )}

        {phase === "arrived" && (
          <section className={styles.centerCard} role="status">
            <span className={`${styles.stateIcon} ${styles.toneSafe}`}>
              <MapPinIcon size={26} />
            </span>
            <h1 className={styles.centerTitle}>목적지에 도착했어요</h1>
            <p className={styles.centerSub}>{destination?.label}</p>
            <button type="button" className={styles.startButton} onClick={reset}>
              새 목적지 설정
            </button>
          </section>
        )}

        <MapControls
          className={styles.controls}
          onZoomIn={() => mapRef.current?.zoomIn()}
          onZoomOut={() => mapRef.current?.zoomOut()}
          onLocate={myLocation ? () => mapRef.current?.panTo(myLocation) : undefined}
        >
          <a href="tel:112" className={`${styles.sideButton} ${styles.sos}`} aria-label="112 긴급 신고 전화">
            <PhoneIcon size={18} />
            <span>SOS</span>
          </a>
          <button
            type="button"
            className={styles.sideButton}
            onClick={shareLocation}
            disabled={!myLocation}
            aria-label="내 위치 공유"
          >
            <ShareIcon size={18} />
            <span>위치공유</span>
          </button>
        </MapControls>

        {toast && (
          <p className={styles.toast} role="status">
            {toast}
          </p>
        )}
      </div>
    </main>
  );
}
