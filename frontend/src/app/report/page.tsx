"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { routeSafety, spotReport, type NearbyFacilityObservation, type RouteResult, type SpotReport } from "@/lib/api";
import { HAVEN_LABEL, havenAvailabilityText, havenDirectionsUrl } from "@/lib/havens";
import { nearestSubway } from "@/lib/kakao";
import { placeFromQuery, placeQuery, resolvePlace, type Place } from "@/lib/place";
import { routeTimeFor } from "@/lib/preferences";
import { environmentPeekText, environmentScoreText, formatDistance, guideOptions, pathLength, walkingMinutes } from "@/lib/routeGuidance";
import { RouteEnvironmentDetails, RouteEnvironmentSummary } from "@/components/RouteEnvironmentSummary";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import { AppHeader } from "@/components/AppHeader";
import { withSearch } from "@/components/WithSearch";
import { AlertIcon, InfoIcon, SearchIcon } from "@/components/icons";
import shared from "../me/me.module.css";
import styles from "./report.module.css";

// 집에서 이 거리 안의 지하철역만 "가까운 역"으로 본다 — 더 멀면 걸어서 귀가하는 길이 아니다.
const STATION_RADIUS_M = 3000;

type NightWalk =
  | { status: "ok"; station: Place; route: RouteResult; comparisonM: number | null }
  | { status: "none" | "error" };

function scoreTone(score: number): string {
  if (score >= 70) return styles.safe;
  if (score >= 40) return styles.caution;
  return styles.warning;
}

function Score({ value, label }: { value: number | null; label: string }) {
  return (
    <div className={styles.score}>
      <span>{label}</span>
      {value === null ? <strong>자료 없음</strong> : <strong className={scoreTone(value)}>{value.toFixed(0)}점</strong>}
    </div>
  );
}

const FACILITY_LABELS: Record<string, string> = {
  cctv: "CCTV", lighting: "보안등", bell: "비상벨", store: "상점", open_store: "영업 확인 상점",
  store_with_published_hours: "공개 시간표가 있는 상점",
};

const LOCAL_STATE = {
  present: "인접 근거 있음",
  absent_in_verified_inventory: "검증 목록에서 인접 시설 미관측",
  unknown: "자료 미확인",
};

const KST_TIME = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

function Count({ observation, label }: { observation?: NearbyFacilityObservation; label: string }) {
  const count = observation?.count;
  return (
    <div className={styles.count}>
      <span>{label}</span>
      <strong>{count == null ? "자료 미확인" : `확인된 ${count}개`}</strong>
    </div>
  );
}

function areaUnavailable(report: SpotReport): string {
  if (report.status === "pending" || !report.status) return "주변 보행 평가 자료를 준비 중이에요.";
  if (report.unavailable_reason === "no_walk_samples") return "이 반경에서 평가할 보행로를 찾지 못했어요.";
  if (report.unavailable_reason === "walk_sample_limit_exceeded") return "이 반경의 보행로가 너무 많아 주변 평가를 제공하지 못했어요.";
  return "주변 보행 시설을 평가할 자료가 충분하지 않아요.";
}

async function loadNightWalk(home: Place, now: Date): Promise<NightWalk> {
  const station = await nearestSubway(home.lat, home.lng, STATION_RADIUS_M);
  if (!station) return { status: "none" };
  const route = await routeSafety(station.lat, station.lng, home.lat, home.lng, { at: routeTimeFor("night", now) });
  const comparisonM = route.shortest_route_points ? pathLength(route.shortest_route_points) : null;
  return { status: "ok", station: { lat: station.lat, lng: station.lng, label: station.name }, route, comparisonM };
}

export default withSearch(ReportPage);

function ReportPage({ search }: { search: string }) {
  const user = useSessionUser();
  const [initial] = useState(() => placeFromQuery(search, "at"));
  const [query, setQuery] = useState(initial?.label ?? "");
  const [place, setPlace] = useState<Place | null>(initial);
  const [report, setReport] = useState<SpotReport | null>(null);
  const [walk, setWalk] = useState<NightWalk | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!place) return;
    let cancelled = false;
    const now = new Date();
    const controller = new AbortController();
    spotReport(place.lat, place.lng, { at: now.toISOString(), signal: controller.signal })
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "리포트를 불러오지 못했어요");
      });
    loadNightWalk(place, now)
      .then((w) => {
        if (!cancelled) setWalk(w);
      })
      .catch(() => {
        if (!cancelled) setWalk({ status: "error" });
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [place]);

  async function handleSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const found = await resolvePlace(query);
    if (!found) {
      setError("주소를 찾을 수 없어요. 도로명이나 지번 주소를 정확히 입력해주세요");
      return;
    }
    setError(null);
    setReport(null);
    setWalk(null);
    setPlace(found);
    window.history.replaceState(null, "", `/report?${placeQuery("at", found)}`);
  }

  if (!user) return null;
  const loading = place !== null && report === null && error === null;
  const nightOption = walk?.status === "ok" ? guideOptions(walk.route)[0] : undefined;
  const nightAssessment = nightOption?.environmentAssessment;
  const safeDistanceM = nightOption?.distanceM ?? 0;
  const hasCompositeScore = environmentScoreText(nightAssessment) !== undefined;

  return (
    <main className={shared.page}>
      <AppHeader userInitial={userInitial(user)} />
      <div className={shared.shell}>
        <section className={shared.infoCard}>
          <h1 className={shared.infoTitle}>
            <InfoIcon size={16} />집 주소 안전 리포트
          </h1>
          <p className={shared.infoText}>
            살 집을 보러 가기 전에 주소를 넣어 보세요. 집 주변 300m의 낮·밤 보행 시설 접근성, 가까운 파출소·편의점·비상벨,
            가장 가까운 역에서 집까지 <strong>밤 귀갓길</strong>을 한 번에 보여드려요.
          </p>
          <form className={styles.search} onSubmit={handleSearch} role="search">
            <SearchIcon size={18} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="예: 경기도 수원시 팔달구 효원로 241"
              aria-label="집 주소"
            />
            <button type="submit">리포트 보기</button>
          </form>
        </section>

        {error && (
          <p className={styles.error} role="alert">
            <AlertIcon size={16} /> {error}
          </p>
        )}
        {loading && <p className={shared.infoText}>{place.label} 주변을 분석하는 중이에요…</p>}

        {report && (
          <>
            {report.zone && (
              <section className={shared.card}>
                <h2 className={shared.cardTitle}>동네 안전지수 · {report.zone.dong_name}</h2>
                <div className={styles.scoreRow}>
                  <Score label="낮" value={report.zone.day_safety_score} />
                  <Score label="밤" value={report.zone.night_safety_score} />
                  <div className={styles.score}>
                    <span>경기도 순위 (지금 시간 기준)</span>
                    <strong>
                      {report.zone.rank}위 <small>/ {report.zone.total}개 동</small>
                    </strong>
                  </div>
                </div>
              </section>
            )}

            <section className={shared.card}>
              <h2 className={shared.cardTitle}>집 주변 {report.radius_m}m 보행 시설 접근성</h2>
              {report.status === "unavailable" || !report.area_environment ? (
                <p className={shared.infoText}>{areaUnavailable(report)}</p>
              ) : (
                <div className={styles.scoreRow}>
                  {(["day", "night"] as const).map((period) => (
                    <div className={styles.score} key={period}>
                      <span>{period === "day" ? "낮" : "밤"}</span>
                      <strong>{environmentPeekText(report.area_environment?.[period])}</strong>
                    </div>
                  ))}
                </div>
              )}
              <div className={styles.countRow}>
                {(["cctv", "lighting", "bell", "store"] as const).map((key) => (
                  <Count key={key} label={FACILITY_LABELS[key]} observation={report.facility_observations?.[key]} />
                ))}
              </div>
              {report.area_environment && (
                <details className={styles.details}>
                  <summary>평가 상세</summary>
                  {Object.entries(report.area_environment).map(([period, value]) => (
                    <p key={period}>{period === "day" ? "낮" : "밤"} <time dateTime={value.reference_at}>{KST_TIME.format(new Date(value.reference_at))}</time> 기준 · 평가 보행로 {value.sampled_length_m === 0 ? "0m" : formatDistance(value.sampled_length_m)}
                      {value.sampled_length_m > 0 && ` · 시설 근거가 확인된 길이 ${((value.verified_distance_ratio ?? 0) * 100).toFixed(0)}%`}
                      {value.used_factors.length > 0 && ` · 사용 지표: ${value.used_factors.map((factor) => FACILITY_LABELS[factor] ?? factor).join(", ")}`}
                    </p>
                  ))}
                  <p>공개 자료와 지도에 있는 보행로 기준이에요. 확인된 시설 수는 주변 전체 시설 수와 다를 수 있어요.</p>
                </details>
              )}
            </section>

            <section className={shared.card}>
              <h2 className={shared.cardTitle}>가까운 시설 확인</h2>
              {report.local_environment ? (
                <>
                  <p className={shared.infoText}>입력한 위치 · <time dateTime={report.local_environment.assessed_at}>{KST_TIME.format(new Date(report.local_environment.assessed_at))}</time> 기준</p>
                  <ul className={styles.localEvidence}>
                    {Object.entries(report.local_environment.factors).map(([factor, value]) => (
                      <li key={factor}>{FACILITY_LABELS[factor] ?? factor}: {LOCAL_STATE[value.state]}</li>
                    ))}
                  </ul>
                </>
              ) : <p className={shared.infoText}>이 위치의 시설 확인 자료가 아직 준비되지 않았어요.</p>}
            </section>

            <section className={shared.card}>
              <h2 className={shared.cardTitle}>가까운 안심 거점</h2>
              {report.havens.length === 0 ? (
                <p className={shared.infoText}>현재 자료에서 1.5km 안의 안심 거점을 확인하지 못했어요.</p>
              ) : (
                <ul className={styles.havens}>
                  {report.havens.map((h) => (
                    <li key={h.kind}>
                      <span>{HAVEN_LABEL[h.kind]} <small>{havenAvailabilityText(h)}</small><small>{h.source_label}</small></span>
                      <strong>{formatDistance(h.distance_m)}</strong>
                      <a href={havenDirectionsUrl(h)} target="_blank" rel="noopener noreferrer">
                        위치 보기
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}

        {place && walk && (
          <section className={shared.card}>
            <h2 className={shared.cardTitle}>역에서 집까지 밤 귀갓길</h2>
            {walk.status === "none" && <p className={shared.infoText}>3km 안에 지하철역이 없어요.</p>}
            {walk.status === "error" && (
              <p className={shared.infoText}>귀갓길을 계산하지 못했어요. 잠시 후 다시 시도해주세요.</p>
            )}
            {walk.status === "ok" && (
              <>
                <p className={shared.infoText}>
                  <strong>{walk.station.label}</strong>에서 밤 11시에 걸어서 귀가한다고 가정했어요.
                </p>
                <div className={styles.scoreRow}>
                  <div className={styles.score}>
                    <span>{hasCompositeScore ? "추천 경로 시설 평가" : "밤 귀갓길 시설 평가"}</span>
                    <div><RouteEnvironmentSummary assessment={nightAssessment} /></div>
                  </div>
                  <div className={styles.score}>
                    <span>거리 · 걸음</span>
                    <strong>
                      {formatDistance(safeDistanceM)} · {walkingMinutes(safeDistanceM)}분
                    </strong>
                  </div>
                  {walk.comparisonM !== null && (
                    <div className={styles.score}>
                      <span>일반 비교 경로</span>
                      <strong>{formatDistance(walk.comparisonM)}</strong>
                    </div>
                  )}
                </div>
                <RouteEnvironmentDetails assessment={nightAssessment} />
                <Link
                  className={styles.action}
                  href={`/route?${placeQuery("start", walk.station)}&${placeQuery("end", place)}`}
                >
                  지도에서 경로 보기
                </Link>
              </>
            )}
          </section>
        )}

        {report && (
          <p className={shared.infoText}>
            공개 데이터로 만든 참고 점수예요. 실제 안전을 보장하지 않으니 집을 보러 갈 때 밤에 한 번 직접 걸어 보세요.{" "}
            <Link href="/data">데이터 출처</Link>
          </p>
        )}
      </div>
    </main>
  );
}
