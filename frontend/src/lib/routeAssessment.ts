import type { RouteAlternative, RouteEnvironmentAssessment, RouteResult } from "./api";

export type RouteScoreSource = {
  safety_score?: number | null;
  environment_assessment?: RouteEnvironmentAssessment | null;
  environment_model_applied?: boolean;
};
export type RouteScoreDisplay = {
  kind: "composite" | "reference" | "partial" | "observed" | "unavailable" | "legacy";
  text: string;
  value: number | null;
  toneValue: number | null;
  rankable: boolean;
};

export const FACILITY_LABEL: Record<string, string> = {
  cctv: "CCTV", lighting: "보안등", open_store: "영업 확인 상점", bell: "비상벨",
  store: "상점", store_with_published_hours: "시간표가 있는 상점",
};
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

export function hasEnvironmentAssessment(source: RouteScoreSource): boolean {
  return source.environment_model_applied === true || source.environment_assessment != null;
}

// Borrow the root only for the first candidate with the exact same path.
export function alternativeAssessment(result: RouteResult, alternative?: RouteAlternative): RouteScoreSource {
  const sharesRootPath = alternative != null && alternative === result.alternatives[0] && alternative.route_points.length > 0
    && alternative.route_points.length === result.route_points.length
    && alternative.route_points.every((point, index) => point.lat === result.route_points[index].lat && point.lng === result.route_points[index].lng);
  return {
    safety_score: alternative ? alternative.safety_score : result.safety_score,
    environment_model_applied: result.environment_model_applied || result.environment_assessment != null,
    environment_assessment: alternative
      ? alternative.environment_assessment ?? (sharesRootPath ? result.environment_assessment : undefined)
      : result.environment_assessment,
  };
}

export function comparisonAssessment(result: RouteResult): RouteScoreSource {
  return { environment_model_applied: hasEnvironmentAssessment(result), environment_assessment: result.comparison_environment_assessment };
}

// Formats the returned value; no score recomputation, averaging or substitution.
export function routeScore(source: RouteScoreSource): RouteScoreDisplay {
  const neutral = (kind: RouteScoreDisplay["kind"], text: string, value: number | null = null): RouteScoreDisplay =>
    ({ kind, text, value, toneValue: null, rankable: false });
  if (hasEnvironmentAssessment(source)) {
    const assessment = source.environment_assessment;
    if (!assessment || assessment.status === "unavailable") return neutral("unavailable", "시설 점수 미산정");
    const basis = assessment.evaluation_basis ?? (finite(assessment.score) ? "multi_factor" : "unavailable");
    if (basis === "multi_factor" && finite(assessment.score)) {
      return { kind: "composite", text: `시설 ${assessment.score.toFixed(0)}점`, value: assessment.score, toneValue: assessment.score, rankable: true };
    }
    if (basis === "single_factor" && finite(assessment.reference_score)) {
      const factor = FACILITY_LABEL[assessment.reference_factor ?? ""] ?? "단일 지표";
      return neutral("reference", `${factor} 참고 ${assessment.reference_score.toFixed(0)}점`, assessment.reference_score);
    }
    if (basis === "partial_coverage") return neutral("partial", "부분자료 평가");
    if (basis === "observed_only") return neutral("observed", "확인된 시설 정보만 제공");
    return neutral("unavailable", "시설 점수 미산정");
  }
  if (finite(source.safety_score)) {
    return { kind: "legacy", text: `참고 안전지수 ${source.safety_score.toFixed(0)}점`, value: source.safety_score, toneValue: source.safety_score, rankable: true };
  }
  return neutral("unavailable", "안전지수 미제공");
}

export function routeRankingAvailable(result: RouteResult): boolean {
  const sources = result.alternatives.map(alternative => alternativeAssessment(result, alternative));
  if (!sources.length || sources.some(source => !routeScore(source).rankable)) return false;
  if (sources.every(source => routeScore(source).kind === "legacy")) return true;
  const assessments = sources.map(source => source.environment_assessment);
  const first = assessments[0];
  return Boolean(first?.comparison_group_id) && assessments.every(assessment =>
    assessment?.comparison_group_id === first?.comparison_group_id && assessment?.model_version === first?.model_version
      && assessment?.policy_version === first?.policy_version && assessment?.period === first?.period);
}
