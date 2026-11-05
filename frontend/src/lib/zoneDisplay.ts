import type { DisplayMetric, FacilityZoneAssessment, ZoneLocation } from "./api";

export type DisplayZone = ZoneLocation & { safety_score?: number; assessment?: FacilityZoneAssessment };
export type ZoneDisplayValue = { text: string; value: number | null };

export const ZONE_FACTOR_LABELS: Record<string, string> = {
  bell: "비상벨", cctv: "CCTV", lighting: "보안등", open_store: "영업 확인 상점",
};

export function factorNames(factors: string[]): string {
  return factors.map(factor => ZONE_FACTOR_LABELS[factor] ?? factor).join(" · ");
}

export function zoneDisplay(zone: DisplayZone, metric: DisplayMetric): ZoneDisplayValue {
  if (metric === "regional_statistics") {
    const score = zone.safety_score;
    return score != null && Number.isFinite(score) ? { value: score, text: `${score.toFixed(0)}점` } : { value: null, text: "자료 없음" };
  }
  const assessment = zone.assessment;
  if (assessment?.evaluation_basis === "multi_factor" && assessment.score != null)
    return { value: assessment.score, text: `시설 ${assessment.score.toFixed(0)}점` };
  if (assessment?.evaluation_basis === "single_factor" && assessment.reference_score != null)
    return { value: null, text: `${factorNames([assessment.reference_factor ?? "시설"])} 참고 ${assessment.reference_score.toFixed(0)}점` };
  if (assessment?.evaluation_basis === "partial_coverage" && assessment.score_bounds)
    return { value: null, text: `부분자료 ${Math.floor(assessment.score_bounds.lower)}~${Math.ceil(assessment.score_bounds.upper)}점` };
  return { value: null, text: assessment?.status === "pending" ? "시설 평가 준비 중" :
    assessment?.unavailable_reason?.startsWith("boundary_") ? "경계 자료 미확인" :
    assessment?.unavailable_reason === "no_walk_samples" ? "평가 보행로 없음" : "시설 자료 미확인" };
}

export function zoneDisplayColor(value: number | null): string {
  if (value == null) return "#64748b";
  if (value >= 70) return "#2e7d32";
  if (value >= 40) return "#f9a825";
  return "#c62828";
}
