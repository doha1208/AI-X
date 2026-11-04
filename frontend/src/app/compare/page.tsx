"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { zoneDetail, type SafetyZoneDetail } from "@/lib/api";
import { loadWatchedZones } from "@/lib/watchedZones";
import { userInitial, useSessionUser } from "@/lib/useSessionUser";
import { AppHeader } from "@/components/AppHeader";
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

export default function ComparePage() {
  const user = useSessionUser();
  const [watched] = useState(loadWatchedZones);
  const [zones, setZones] = useState<SafetyZoneDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (watched.length < 2) return;
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
  }, [watched]);

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
            관심 동네로 저장한 곳을 요소별로 나란히 비교해요. 줄마다 가장 좋은 값을 <strong>초록색</strong>으로
            표시했어요. 지자체가 자료를 내지 않은 항목은 &lsquo;자료 없음&rsquo;으로 두고 점수 계산에서도 뺐어요.
          </p>
        </section>

        {watched.length < 2 && (
          <section className={shared.card}>
            <p className={shared.infoText}>
              비교하려면 관심 동네가 2곳 이상 필요해요. <Link href="/">안심 거주지</Link> 순위에서 &lsquo;관심&rsquo;을 눌러
              저장해 주세요.
            </p>
          </section>
        )}
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        {watched.length >= 2 && !zones && !error && <p className={shared.infoText}>불러오는 중…</p>}

        {zones && (
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
