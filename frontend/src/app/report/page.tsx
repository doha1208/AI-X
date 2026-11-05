"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { routeSafety, spotReport, type RouteResult, type SpotReport } from "@/lib/api";
import { HAVEN_LABEL, havenDirectionsUrl } from "@/lib/havens";
import { nearestSubway } from "@/lib/kakao";
import { placeFromQuery, placeQuery, resolvePlace, type Place } from "@/lib/place";
import { routeTimeFor } from "@/lib/preferences";
import { environmentScoreText, formatDistance, guideOptions, pathLength, walkingMinutes } from "@/lib/routeGuidance";
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

function Count({ value, label }: { value: number | null | undefined; label: string }) {
  const unknown = value === null || value === undefined;
  return (
    <div className={styles.count}>
      <strong>{unknown ? "–" : value}</strong>
      <span>{unknown ? `${label} (자료 없음)` : label}</span>
    </div>
  );
}

async function loadNightWalk(home: Place): Promise<NightWalk> {
  const station = await nearestSubway(home.lat, home.lng, STATION_RADIUS_M);
  if (!station) return { status: "none" };
  const route = await routeSafety(station.lat, station.lng, home.lat, home.lng, { at: routeTimeFor("night") });
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
    spotReport(place.lat, place.lng)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "리포트를 불러오지 못했어요");
      });
    loadNightWalk(place)
      .then((w) => {
        if (!cancelled) setWalk(w);
      })
      .catch(() => {
        if (!cancelled) setWalk({ status: "error" });
      });
    return () => {
      cancelled = true;
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
            살 집을 보러 가기 전에 주소를 넣어 보세요. 그 집 주변 300m의 낮·밤 안전 점수, 가까운 파출소·편의점·비상벨,
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
              <h2 className={shared.cardTitle}>집 주변 {report.radius_m}m</h2>
              <div className={styles.scoreRow}>
                <Score label="낮 골목 점수" value={report.area_day_score} />
                <Score label="밤 골목 점수" value={report.area_night_score} />
              </div>
              <div className={styles.countRow}>
                <Count label="CCTV" value={report.counts?.cctv} />
                <Count label="보안등" value={report.counts?.lights} />
                <Count label="편의점" value={report.counts?.convenience} />
              </div>
            </section>

            <section className={shared.card}>
              <h2 className={shared.cardTitle}>가까운 안심 거점</h2>
              {report.havens.length === 0 ? (
                <p className={shared.infoText}>1.5km 안에 파출소·24시 편의점·비상벨이 없어요.</p>
              ) : (
                <ul className={styles.havens}>
                  {report.havens.map((h) => (
                    <li key={h.kind}>
                      <span>{HAVEN_LABEL[h.kind]}</span>
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
