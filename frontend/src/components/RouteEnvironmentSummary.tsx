import type { RouteEnvironmentAssessment } from "@/lib/api";
import { environmentScoreText, formatDistance, supportedEnvironment } from "@/lib/routeGuidance";
import styles from "./RouteEnvironmentSummary.module.css";

const FACTORS: Record<string, string> = { cctv: "CCTV", lighting: "보안등", open_store: "영업 확인 상점", store: "상점", bell: "비상벨", store_with_published_hours: "영업시간 자료가 있는 상점" };
const REASONS: Record<string, string> = {
  source_missing: "시설 평가 입력이 아직 준비되지 않았어요.",
  provenance_unverified: "좌표는 있지만 원본 출처와 기준일 확인이 필요해요.",
  coverage_unverified: "이 지역의 수집 범위와 좌표 누락 확인이 필요해요.",
  purpose_unverified: "방범 목적의 CCTV인지 확인이 필요해요.",
  opening_hours_unverified: "상점의 요일·시간별 영업 근거가 충분하지 않아요.",
  outside_source_coverage: "검증된 조사 범위가 이 경로 전체를 포함하지 않아요.",
  verified_complete_coverage_required: "경로 주변을 빠짐없이 포함하는 검증된 자료가 필요해요.",
};

export function RouteEnvironmentSummary({ assessment }: { assessment?: RouteEnvironmentAssessment | null }) {
  const score = environmentScoreText(assessment);
  return <span className={`${styles.summary} ${score ? styles.scored : styles.pending}`}>{score ? `시설 ${score}` : "점수 미산정"}</span>;
}

export function RouteEnvironmentDetails({ assessment }: { assessment?: RouteEnvironmentAssessment | null }) {
  const value = supportedEnvironment(assessment);
  return (
    <details className={styles.details}>
      <summary>평가 상세</summary>
      <div className={styles.content}>
        {environmentScoreText(value) ? (
          <p>시설 접근성 지수는 공개 자료에서 확인된 시설과 경로의 가까운 정도예요.</p>
        ) : (
          <p>종합 점수를 계산할 검증 지표가 부족해요. 확인된 시설 좌표는 아래에 표시해요.</p>
        )}
        {value && <>
          {Object.keys(value.observed_facility_counts ?? {}).length > 0 && (
            <p>자료에서 확인한 주변 시설 좌표: {Object.entries(value.observed_facility_counts ?? {}).map(([factor, count]) => `${FACTORS[factor] ?? factor} ${count}개`).join(" · ")}</p>
          )}
          {(value.observed_facility_counts?.store_with_published_hours ?? 0) > 0 && <p>영업시간 자료는 일부 매장만 포함하며 방문 시각의 영업·유인 여부와 달라요.</p>}
          <p>{value.longest_support_gap_m == null ? "시설 공백 확인 불가" : `최장 시설 공백 ${value.longest_support_gap_m === 0 ? "0m" : formatDistance(value.longest_support_gap_m)}`}</p>
          <p>사용 지표 {value.used_factors.length}/{value.active_factors.length}{value.used_factors.length > 0 ? ` · ${value.used_factors.map((k) => FACTORS[k] ?? k).join(", ")}` : ""}</p>
          {Object.keys(value.excluded_factors).length > 0 && <>
            <p>평가 제외</p>
            <ul>{Object.entries(value.excluded_factors).map(([factor, reason]) => (
              <li key={factor}>{FACTORS[factor] ?? factor}: {REASONS[reason] ?? "평가에 필요한 자료를 확인할 수 없어요."}</li>
            ))}</ul>
          </>}
        </>}
        <p>자료 부족은 주변에 시설이 없다는 뜻은 아니에요. 비교 경로에는 같은 지표를 적용해요.</p>
        <p>공개된 설치 위치 기준이며, 실제 시설의 전수조사나 현재 작동 여부를 확인한 점수는 아니에요.</p>
      </div>
    </details>
  );
}
