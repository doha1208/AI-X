"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { routeSafety, type RoutePeriod, type SafetyZone } from "@/lib/api";
import { haversineMeters } from "@/lib/geo";
import type { LatLng } from "@/lib/kakao";
import { acceptFix, GEO_OPTIONS, toFix, type Fix } from "@/lib/locationFilter";
import { loadHandoff } from "@/lib/guideHandoff";
import { placeFromQuery, placeQuery, resolvePlace, type Place } from "@/lib/place";
import {
  addRecent,
  loadEmergencyContacts,
  loadRecent,
  loadSettings,
  routeTimeFor,
  saveSettings,
  type Settings,
} from "@/lib/preferences";
import {
  formatDistance,
  guideOptions,
  nearestPointOnPath,
  nextTurn,
  progressAlong,
  walkingMinutes,
  type GuideKind,
  type GuideOption,
  type TurnDirection,
} from "@/lib/routeGuidance";
import { useMyLocation } from "@/lib/useMyLocation";
import { useRouteBells } from "@/lib/useRouteBells";
import { useWakeLock } from "@/lib/useWakeLock";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import { AppHeader } from "@/components/AppHeader";
import { ChoicePanel } from "./ChoicePanel";
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

const ARRIVAL_RADIUS_M = 30;
// 가장 가까운 경로 지점에서 이보다 멀어지면 경로를 벗어난 것으로 보고 다시 찾는다.
const OFF_ROUTE_M = 40;
const REROUTE_MIN_INTERVAL_MS = 5000;
const TOAST_MS = 2500;
// 목적지까지 이보다 가까워지면 한 번 "곧 도착"을 안내한다(30m 도착 안내와는 별개).
const NEAR_ARRIVAL_M = 100;
// 이 점수 미만이면 scoreLevel()이 "주의"로 분류한다 — 새로 진입할 때 한 번 음성으로 알린다.
const CAUTION_SCORE = 40;
// 내 위치가 경로에서 이 거리 안이면 GPS 떨림을 줄이려고 마커를 경로 위로 붙여서 보여준다.
const SNAP_TO_ROUTE_M = 25;

const TURN_TEXT: Record<TurnDirection, string> = { left: "좌회전", right: "우회전", arrive: "앞 목적지" };

function scoreLevel(score: number): { label: string; tone: string } {
  if (score >= 70) return { label: "안전", tone: styles.toneSafe };
  if (score >= CAUTION_SCORE) return { label: "보통", tone: styles.toneCaution };
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
  const [settings, setSettings] = useState(loadSettings);
  const [voicePanelOpen, setVoicePanelOpen] = useState(false);
  const [recent] = useState(() => loadRecent("destinations"));
  const [destination, setDestination] = useState<Place | null>(() =>
    placeFromQuery(search, "end")
  );
  const [position, setPosition] = useState<LatLng | null>(null);
  // 목적지를 정하면 먼저 안전 경로·최단 경로를 보여주고(choice), 고른 경로(mode)로 안내한다(guided).
  // 길찾기 탭에서 이미 경로를 골라 넘어온 경우(?mode=safe|shortest)에는 고르는 단계를 건너뛴다.
  const [choice, setChoice] = useState<{ options: GuideOption[]; safetyWeighted: boolean; period: RoutePeriod } | null>(
    null
  );
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
  // 길찾기에서 고른 출발지가 지금 위치와 다를 때, 새 경로를 찾는 대신 먼저 그 출발점으로
  // 이동하라고 안내한다(경로 첫 지점 근처에 아직 못 왔을 때만 — progress.index === 0).
  const [headingToStart, setHeadingToStart] = useState(false);
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
        setChoice({ options: found, safetyWeighted: result.mode === "safety_weighted", period: result.period });
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
    const progress = guided ? progressAlong(guided.points, here) : null;
    if (progress && progress.offRouteM <= OFF_ROUTE_M) {
      onRouteOnceRef.current = true;
      setHeadingToStart(false);
      return;
    }
    if (progress && progress.index === 0 && !onRouteOnceRef.current) {
      // 아직 경로에 한 번도 올라서지 못했다 — 새 경로를 찾지 않고 출발점으로 걸어오라고만 안내한다.
      // (경로 위를 걷다 첫 구간에서 벗어난 경우는 여기 걸리지 않고 재탐색된다.)
      setHeadingToStart(true);
      return;
    }
    setHeadingToStart(false);
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

  useWakeLock(settings.keepScreenOn && mode !== null && !arrived && !denied && destination !== null);

  useEffect(() => {
    if (!headingToStart || !settings.voiceOn) return;
    speak("먼저 출발지까지 이동해주세요", settings.voiceVolume);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headingToStart, settings.voiceOn]);

  const wasReroutingRef = useRef(false);
  useEffect(() => {
    if (rerouting && !wasReroutingRef.current && settings.voiceOn) {
      speak("경로를 벗어나 다시 찾을게요", settings.voiceVolume);
    }
    wasReroutingRef.current = rerouting;
  }, [rerouting, settings.voiceOn, settings.voiceVolume]);

  const cautionZoneCode = guidance?.zone && guidance.zone.safety_score < CAUTION_SCORE ? guidance.zone.dong_code : null;
  useEffect(() => {
    if (!cautionZoneCode || !settings.voiceOn) return;
    speak("주의 구역에 들어섰어요", settings.voiceVolume);
    // 같은 주의 구역 안에서 위치가 갱신될 때마다 다시 말하지 않도록 동 코드가 바뀔 때만 반응한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cautionZoneCode, settings.voiceOn]);

  const announcedNearArrivalRef = useRef(false);
  const onRouteOnceRef = useRef(false);
  useEffect(() => {
    announcedNearArrivalRef.current = false; // 새 경로를 시작하면 다시 안내할 수 있게 초기화한다.
    onRouteOnceRef.current = false;
  }, [guided]);
  useEffect(() => {
    const remaining = guidance?.progress.remainingM;
    if (remaining === undefined || remaining > NEAR_ARRIVAL_M || announcedNearArrivalRef.current) return;
    announcedNearArrivalRef.current = true;
    if (settings.voiceOn) speak(`목적지까지 ${formatDistance(remaining)} 남았어요`, settings.voiceVolume);
  }, [guidance, settings.voiceOn, settings.voiceVolume]);

  // GPS 떨림 때문에 내 위치 마커가 경로 옆에서 흔들리지 않도록, 경로에 충분히 가까우면
  // 마커를 경로 위 가장 가까운 지점에 붙여서 보여준다(실제 위치 계산에는 원본 좌표를 그대로 쓴다).
  const snappedLocation = useMemo(() => {
    if (!mode || !guided || !position || arrived || guided.points.length < 2) return null;
    const snapped = nearestPointOnPath(guided.points, position);
    return snapped.distanceM <= SNAP_TO_ROUTE_M ? snapped.point : null;
  }, [mode, guided, position, arrived]);

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
    setHeadingToStart(false);
    setRouteError(null);
  }

  function startTo(place: Place) {
    clearRoute();
    setDestination(place);
    stopPicking();
    setChooseError(null);
    lastFetchAtRef.current = 0;
    addRecent("destinations", place);
    window.history.replaceState(null, "", `/navigate?${placeQuery("end", place)}`);
    // 위치가 이미 있으면 다음 GPS 갱신을 기다리지 않고 바로 두 경로를 비교한다.
    const here = position ?? location;
    if (here) void fetchRoute(here, place, "options", false);
  }

  function chooseOption(option: GuideOption) {
    setMode(option.kind);
    setGuided(option);
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

  function locationLink(here: LatLng): string {
    return `https://map.kakao.com/link/map/${encodeURIComponent("내 현재 위치")},${here.lat},${here.lng}`;
  }

  async function shareLocation() {
    const here = position ?? location;
    if (!here) return;
    const url = locationLink(here);
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

  // 등록해 둔 보호자 번호로 현재 위치가 담긴 SMS 초안을 연다 — 실제 발송은 사용자가 문자
  // 앱에서 직접 눌러야 하고, 여기서 자동으로 보내지 않는다.
  function smsGuardians() {
    const here = position ?? location;
    if (!here) {
      showToast("현재 위치를 아직 찾지 못했어요");
      return;
    }
    const contacts = loadEmergencyContacts();
    if (contacts.length === 0) {
      showToast("내 정보에서 긴급 연락처를 먼저 등록해주세요");
      return;
    }
    const body = `[긴급] 도움이 필요해요. 지금 위치: ${locationLink(here)}`;
    const numbers = contacts.map((c) => c.phone.replace(/[^\d+]/g, "")).join(",");
    // iOS는 전화번호 뒤에 ?가 아니라 &로 body를 붙여야 인식한다.
    const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    window.location.href = `sms:${numbers}${isIOS ? "&" : "?"}body=${encodeURIComponent(body)}`;
  }

  if (!user) return null;

  const myLocation = position ?? location ?? undefined;
  const displayLocation = snappedLocation ?? myLocation;
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

      <div className={styles.stage}>
        <SafetyMap
          ref={mapRef}
          bells={phase === "guiding" ? routeBells : undefined}
          center={displayLocation}
          myLocation={displayLocation}
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
              ) : headingToStart && guidance ? (
                <>
                  <span className={styles.turnIcon}>
                    <MapPinIcon size={26} />
                  </span>
                  <div className={styles.turnText} aria-live="polite">
                    <p className={styles.turnTitle}>
                      {formatDistance(guidance.progress.offRouteM)}{" "}
                      <span className={styles.turnAction}>출발지로 이동</span>
                    </p>
                    <p className={styles.turnSub}>목적지 · {destination?.label}</p>
                  </div>
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

            <section className={styles.bottomPanel}>
              <div className={styles.stats}>
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
            </section>
          </>
        )}

        {phase === "select" && (
          <ChoicePanel
            destination={destination}
            choice={choice}
            safeOption={safeOption}
            previewOption={previewOption}
            myLocation={myLocation}
            routeError={routeError}
            onPreview={setPreviewKind}
            onChoose={chooseOption}
            onRetry={retryRoute}
            onCancel={reset}
          />
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
                      <button
                        type="button"
                        className={styles.recentItem}
                        onClick={() => startTo({ lat: entry.lat, lng: entry.lng, label: entry.label })}
                      >
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
            onClick={smsGuardians}
            disabled={!myLocation}
            aria-label="보호자에게 위치 문자 보내기"
          >
            <AlertIcon size={18} />
            <span>보호자문자</span>
          </button>
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
