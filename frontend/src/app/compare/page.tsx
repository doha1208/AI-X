"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { zoneDetail, type DisplayMetric, type FacilityZoneResponse, type RoutePeriod, type SafetyZoneDetail } from "@/lib/api";
import { loadWatchedZones } from "@/lib/watchedZones";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import { AppHeader } from "@/components/AppHeader";
import { FacilityBasisPicker } from "@/components/FacilityBasisPicker";
import { withSearch } from "@/components/WithSearch";
import { useFacilityZones } from "@/lib/useFacilityZones";
import { factorNames, zoneDisplay } from "@/lib/zoneDisplay";
import { InfoIcon } from "@/components/icons";
import shared from "../me/me.module.css";
import styles from "../report/report.module.css";

type Row = {
  label: string;
  value: (z: SafetyZoneDetail) => number | null;
  format: (v: number) => string;
  // 높을수록 좋은 요소인지 — 줄마다 가장 좋은 값을 강조할 때 쓴다.
  higherIsBetter: boolean;
};

const meters = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}km` : `${Math.round(v)}m`);

const ROWS: Row[] = [
  { label: "지금 점수", value: (z) => z.safety_score, format: (v) => `${v.toFixed(0)}점`, higherIsBetter: true },
  { label: "낮 점수", value: (z) => z.day_safety_score, format: (v) => `${v.toFixed(0)}점`, higherIsBetter: true },
  { label: "밤 점수", value: (z) => z.night_safety_score, format: (v) => `${v.toFixed(0)}점`, higherIsBetter: true },
  { label: "경기도 순위", value: (z) => z.rank, format: (v) => `${v}위`, higherIsBetter: false },
  { label: "CCTV", value: (z) => z.cctv_count, format: (v) => `${v}대`, higherIsBetter: true },
  { label: "보안등", value: (z) => z.streetlight_count, format: (v) => `${v}개`, higherIsBetter: true },
  { label: "범죄율 (시·군, 1만 명당)", value: (z) => z.crime_rate, format: (v) => `${v.toFixed(1)}건`, higherIsBetter: false },
  { label: "가까운 경찰서·지구대", value: (z) => z.police_dist_m, format: meters, higherIsBetter: false },
  { label: "가까운 비상벨", value: (z) => z.bell_dist_m, format: meters, higherIsBetter: false },
  { label: "교통사고 다발지역까지", value: (z) => z.accident_dist_m, format: meters, higherIsBetter: true },
  {
    label: "밤 유동인구 (시간당)",
    value: (z) => z.night_floating_pop,
    format: (v) => `${Math.round(v).toLocaleString()}명`,
    higherIsBetter: true,
  },
  { label: "상점", value: (z) => z.store_count, format: (v) => `${v}곳`, higherIsBetter: true },
];

function bestValue(row: Pick<Row, "value" | "higherIsBetter">, zones: SafetyZoneDetail[]): number | null {
  const values = zones.map(row.value).filter((v): v is number => v !== null);
  if (values.length < 2) return null;
  return row.higherIsBetter ? Math.max(...values) : Math.min(...values);
}

export default withSearch(ComparePage);

function FacilityComparisonTable({ report }: { report: FacilityZoneResponse }) {
  const comparison = report.comparison;
  if (!comparison) return null;
  const byCode = new Map(report.zones.map(zone => [zone.dong_code, zone]));
  const zones = comparison.dong_codes.flatMap(code => {
    const row = byCode.get(code);
    return row ? [row] : [];
  });
  const common = comparison.evaluation_basis;
  const best = common === "multi_factor" ? Math.max(...Object.values(comparison.scores).map(Math.round)) : null;
  const factors = [...new Set(zones.flatMap(zone => [
    ...Object.keys(zone.assessment.factor_coverage), ...Object.keys(zone.assessment.factor_evaluation_ratio),
  ]))].sort();
  return (
    <section className={`${shared.card} ${styles.tableWrap}`}>
      <p className={shared.infoText}>{common === "not_comparable"
        ? "공통으로 확인된 지표가 없어 점수의 우열을 비교할 수 없어요."
        : `공통 지표: ${factorNames(comparison.used_factors)} · ${common === "single_factor" ? "단일 지표 참고 비율" : "같은 지표로 다시 계산한 시설 접근성"}`}</p>
      <table className={styles.table}>
        <thead><tr><th scope="col">항목</th>{zones.map(zone => <th key={zone.dong_code} scope="col">{zone.dong_name}</th>)}</tr></thead>
        <tbody>
          {common !== "not_comparable" && <tr>
            <th scope="row">{common === "multi_factor" ? "공통 지표 점수" : "공통 지표 참고 비율"}</th>
            {zones.map(zone => {
              const score = comparison.scores[zone.dong_code];
              const value = score == null ? null : Math.round(score);
              return <td key={zone.dong_code} className={best !== null && value === best ? styles.best : undefined}>
                {value === null ? "자료 미확인" : `${value}${common === "multi_factor" ? "점" : "%"}`}
              </td>;
            })}
          </tr>}
          <tr>
            <th scope="row">동네별 평가 (개별 기준)</th>
            {zones.map(zone => <td key={zone.dong_code}>{zoneDisplay(zone, "facility_access").text}</td>)}
          </tr>
          {factors.map(factor => <tr key={factor}>
            <th scope="row">{factorNames([factor])} 접근 비율</th>
            {zones.map(zone => {
              const ratio = zone.assessment.factor_coverage[factor];
              const known = zone.assessment.factor_evaluation_ratio[factor];
              return <td key={zone.dong_code}>{ratio != null ? `${Math.round(ratio * 100)}%` :
                known > 0 ? `접근 비율 미확인 · 근거 확인 ${Math.round(known * 100)}%` : "자료 미확인"}</td>;
            })}
          </tr>)}
        </tbody>
      </table>
    </section>
  );
}

function ComparePage({ search }: { search: string }) {
  const user = useSessionUser();
  const [watched] = useState(loadWatchedZones);
  const [metric, setMetric] = useState<DisplayMetric>(() => new URLSearchParams(search).get("metric") === "facility_access" ? "facility_access" : "regional_statistics");
  const [period, setPeriod] = useState<RoutePeriod | undefined>(() => {
    const requested = new URLSearchParams(search).get("period");
    return requested === "day" || requested === "night" ? requested : undefined;
  });
  const [basisId, setBasisId] = useState<string | undefined>(() => new URLSearchParams(search).get("basis") || undefined);
  const facilityMode = metric === "facility_access";
  const facilityQuery = useFacilityZones(facilityMode && watched.length >= 2, period, basisId, watched.map(row => row.dong_code));
  const [zones, setZones] = useState<SafetyZoneDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (watched.length < 2 || facilityMode) return;
    let cancelled = false;
    Promise.all(watched.map((w) => zoneDetail(w.dong_code)))
      .then((found) => {
        if (!cancelled) setZones(found);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "동네 정보를 불러오지 못했어요");
      });
    return () => {
      cancelled = true;
    };
  }, [watched, facilityMode]);

  if (!user) return null;

  return (
    <main className={shared.page}>
      <AppHeader userInitial={userInitial(user)} />
      <div className={shared.shell}>
        <section className={shared.infoCard}>
          <h1 className={shared.infoTitle}>
            <InfoIcon size={16} />
            관심 동네 비교
          </h1>
          <p className={shared.infoText}>
            {facilityMode
              ? "공개 자료에 있는 시설이 보행로에 얼마나 가까운지 비교해요. 같은 지표로 평가할 수 있는 경우에만 공통 점수를 계산해요."
              : <>지역 통계 지수와 원자료를 요소별로 비교해요. 줄마다 가장 좋은 값을 <strong>초록색</strong>으로 표시해요.</>}
          </p>
          <label>평가 기준{" "}
            <select value={metric} onChange={event => setMetric(event.target.value as DisplayMetric)}>
              <option value="regional_statistics">지역 통계 지수</option>
              <option value="facility_access">보행 시설 접근성</option>
            </select>
          </label>
          {facilityMode && watched.length >= 2 && <FacilityBasisPicker period={period} basisId={basisId}
            report={facilityQuery?.report} changedGroups={facilityQuery?.groups}
            onPeriod={value => { setPeriod(value); setBasisId(undefined); }} onBasis={setBasisId} />}
        </section>

        {watched.length < 2 && (
          <section className={shared.card}>
            <p className={shared.infoText}>
              비교하려면 관심 동네가 2곳 이상 필요해요. <Link href="/">안심 거주지</Link> 순위에서 &lsquo;관심&rsquo;을 눌러
              저장해 주세요.
            </p>
          </section>
        )}
        {(facilityMode ? facilityQuery?.error : error) && (
          <p className={styles.error} role="alert">
            {facilityMode ? facilityQuery?.error : error}
          </p>
        )}
        {watched.length >= 2 && (facilityMode ? !facilityQuery : !zones && !error) && <p className={shared.infoText}>불러오는 중…</p>}
        {facilityMode && facilityQuery?.report?.status === "pending" && <p className={shared.infoText}>동네 시설 평가 자료를 준비 중이에요.</p>}
        {facilityMode && facilityQuery?.report?.status === "available" && <FacilityComparisonTable report={facilityQuery.report} />}

        {!facilityMode && zones && (
          <section className={`${shared.card} ${styles.tableWrap}`}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">항목</th>
                  {zones.map((z) => (
                    <th key={z.dong_code} scope="col">
                      {z.dong_name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => {
                  const best = bestValue(row, zones);
                  return (
                    <tr key={row.label}>
                      <th scope="row">{row.label}</th>
                      {zones.map((z) => {
                        const v = row.value(z);
                        return (
                          <td key={z.dong_code} className={v !== null && v === best ? styles.best : undefined}>
                            {v === null ? "자료 없음" : row.format(v)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        )}
      </div>
    </main>
  );
}
