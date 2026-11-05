import type { RouteScoreSource } from "@/lib/routeAssessment";
import { FACILITY_LABEL, hasEnvironmentAssessment, routeScore } from "@/lib/routeAssessment";
import styles from "./RouteAssessmentSummary.module.css";

const REASON: Record<string, string> = {
  source_missing: "자료 없음", provenance_unverified: "출처 미확인", coverage_unverified: "조사 범위 미확인",
  purpose_unverified: "설치 목적 미확인", opening_hours_unverified: "영업시간 미확인", outside_source_coverage: "자료 범위 밖",
};

export function RouteAssessmentSummary({ source, showScore = true }: { source: RouteScoreSource; showScore?: boolean }) {
  if (!hasEnvironmentAssessment(source)) return null;
  const display = routeScore(source);
  const assessment = source.environment_assessment;
  return <div className={styles.summary} aria-label="경로 시설 평가">
    {showScore && <strong>{display.text}</strong>}
    {assessment && <details>
      <summary>시설 평가 상세</summary>
      <dl>
        <div><dt>사용 지표</dt><dd>{assessment.used_factors.map(factor => FACILITY_LABEL[factor] ?? factor).join(" · ") || "종합 평가 지표 없음"}</dd></div>
        {Object.entries(assessment.excluded_factors).map(([factor, reason]) => <div key={factor}>
          <dt>{FACILITY_LABEL[factor] ?? factor}</dt><dd>{REASON[reason] ?? "평가 근거 미확인"}</dd>
        </div>)}
        {assessment.verified_distance_ratio != null && <div><dt>근거 확인 거리 비율</dt><dd>{Math.round(assessment.verified_distance_ratio * 100)}%</dd></div>}
        {assessment.longest_support_gap_m != null && <div><dt>가장 긴 시설 공백</dt><dd>{Math.round(assessment.longest_support_gap_m)}m</dd></div>}
      </dl>
      {display.kind === "reference" && <p>단일 지표의 참고값이며 종합 점수와 다릅니다.</p>}
      {display.kind === "partial" && <p>일부 구간의 자료만 확인되어 하나의 종합 점수로 표시하지 않습니다.</p>}
    </details>}
  </div>;
}
