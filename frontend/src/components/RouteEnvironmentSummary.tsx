import type { RouteEnvironmentAssessment } from "@/lib/api";
import { environmentScoreText, formatDistance, supportedEnvironment } from "@/lib/routeGuidance";
import styles from "./RouteEnvironmentSummary.module.css";

const FACTORS: Record<string, string> = { cctv: "CCTV", lighting: "보안등", open_store: "영업 확인 상점", bell: "비상벨" };

export function RouteEnvironmentSummary({ assessment }: { assessment?: RouteEnvironmentAssessment | null }) {
  const value = supportedEnvironment(assessment);
  if (!value) return <span className={styles.summary}>시설 평가 데이터 부족</span>;
  const score = environmentScoreText(value);
  return (
    <span className={styles.summary} aria-label="경로 시설 평가">
      <span>{score ? `시설 접근성 지수 ${score}` : "시설 평가 데이터 부족"}</span>
      <span>{value.longest_support_gap_m == null ? "시설 공백 확인 불가" : `최장 시설 공백 ${value.longest_support_gap_m === 0 ? "0m" : formatDistance(value.longest_support_gap_m)}`}</span>
      <span className={styles.detail}>사용 지표 {value.used_factors.length}/{value.active_factors.length}</span>
      {Object.keys(value.excluded_factors).length > 0 && (
        <span className={styles.detail}>평가 제외: {Object.keys(value.excluded_factors).map((k) => FACTORS[k] ?? k).join(", ")}</span>
      )}
    </span>
  );
}
