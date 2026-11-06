import type { DisplayMetric, FacilityBasisGroup, FacilityZone, FacilityZoneResponse, ZoneLocation } from "./api";

export type DisplayZone = ZoneLocation & { safety_score?: number } &
  Partial<Pick<FacilityZone, "assessment" | "rank" | "rank_tied" | "relative_percentile" | "result_group_id">>;
export type ZoneDisplayValue = { text: string; value: number | null; hasFacilityScore?: true };

const SCORE_COLORS = { high: "#2e7d32", middle: "#f9a825", low: "#c62828" };
export const FACILITY_PERCENTILE_CUTOFFS = { middle: 10, high: 60 } as const;
const FACILITY_BANDS = {
  high: { text: "상위권", color: SCORE_COLORS.high },
  middle: { text: "중간권", color: SCORE_COLORS.middle },
  low: { text: "하위권", color: SCORE_COLORS.low },
};

export const ZONE_FACTOR_LABELS: Record<string, string> = {
  bell: "비상벨", cctv: "CCTV", lighting: "보안등", open_store: "영업 확인 상점",
};

export function factorNames(factors: string[]): string {
  return factors.map(factor => ZONE_FACTOR_LABELS[factor] ?? factor).join(" · ");
}

export function facilityAccessScore(zone: DisplayZone): number | null {
  const assessment = zone.assessment;
  const score = assessment?.score;
  return assessment?.evaluation_basis === "multi_factor" && score != null && Number.isFinite(score) ? score : null;
}

export function restoreLegacyFacilityPercentiles(report: FacilityZoneResponse): FacilityZoneResponse {
  if (report.relative_method !== undefined || report.status !== "available") return report;
  const group = report.groups.find(candidate => candidate.basis_id === report.basis_id);
  if (!group || group.relative_status != null) return report;

  const ranksByDong = new Map<string, number>();
  const countsByRank = new Map<number, number>();
  for (const zone of report.zones) {
    if (zone.rank == null || zone.result_group_id !== group.result_group_id ||
        zone.assessment.basis_id !== group.basis_id || facilityAccessScore(zone) == null) continue;
    if (ranksByDong.has(zone.dong_code)) return report;
    ranksByDong.set(zone.dong_code, zone.rank);
    countsByRank.set(zone.rank, (countsByRank.get(zone.rank) ?? 0) + 1);
  }
  // Percentiles require the whole cohort from the same response, even in the nearby view.
  if (ranksByDong.size !== group.zone_count || ranksByDong.size === 0) return report;
  const status = group.zone_count < 20 ? "insufficient_group" : countsByRank.size === 1 ? "no_variation" : "available";
  const percentiles = new Map<number, number>();
  let rankedCount = 0;
  for (const [rank, ties] of [...countsByRank].sort(([a], [b]) => a - b)) {
    if (rank !== rankedCount + 1) return report;
    rankedCount += ties;
    if (status === "available") {
      const lowerCount = group.zone_count - rankedCount;
      percentiles.set(rank, Number((100 * (lowerCount + ties / 2) / group.zone_count).toFixed(1)));
    }
  }
  return {
    ...report,
    groups: report.groups.map(candidate => candidate === group ? { ...group, relative_status: status } : candidate),
    zones: report.zones.map(zone => {
      const rank = ranksByDong.get(zone.dong_code);
      return rank == null ? zone : {
        ...zone,
        rank_tied: (countsByRank.get(rank) ?? 0) > 1,
        relative_percentile: percentiles.get(rank) ?? null,
      };
    }),
  };
}

export function zoneDisplay(zone: DisplayZone, metric: DisplayMetric): ZoneDisplayValue {
  if (metric === "regional_statistics") {
    const score = zone.safety_score;
    return score != null && Number.isFinite(score) ? { value: score, text: `${score.toFixed(0)}점` } : { value: null, text: "자료 없음" };
  }
  const assessment = zone.assessment;
  const score = facilityAccessScore(zone);
  if (score != null) return { value: score, text: `시설 ${score.toFixed(0)}점` };
  if (assessment?.evaluation_basis === "single_factor" && assessment.reference_score != null)
    return { value: null, text: `${factorNames([assessment.reference_factor ?? "시설"])} 참고 ${assessment.reference_score.toFixed(0)}점` };
  if (assessment?.evaluation_basis === "partial_coverage" && assessment.score_bounds)
    return { value: null, text: `부분자료 ${Math.floor(assessment.score_bounds.lower)}~${Math.ceil(assessment.score_bounds.upper)}점` };
  return { value: null, text: assessment?.status === "pending" ? "시설 평가 준비 중" :
    assessment?.unavailable_reason?.startsWith("boundary_") ? "경계 자료 미확인" :
    assessment?.unavailable_reason === "no_walk_samples" ? "평가 보행로 없음" : "시설 자료 미확인" };
}

export function residenceZoneDisplay(zone: DisplayZone, metric: DisplayMetric, group?: FacilityBasisGroup): ZoneDisplayValue {
  if (metric === "regional_statistics") return zoneDisplay(zone, metric);
  const score = facilityAccessScore(zone);
  if (score == null) return zoneDisplay(zone, metric);
  if (group && zone.assessment?.basis_id !== group.basis_id) return { value: null, text: "다른 지표 집단", hasFacilityScore: true };
  const percentile = zone.relative_percentile;
  if (group?.relative_status === "available" && zone.result_group_id === group.result_group_id &&
      percentile != null && Number.isFinite(percentile)) {
    return { value: percentile, text: `백분위 ${percentile.toFixed(1)}` };
  }
  return { value: null, text: `인접 비율 평균 ${score.toFixed(0)}%`, hasFacilityScore: true };
}

export function facilityRankLabel(zone: DisplayZone, group?: FacilityBasisGroup): string | null {
  if (!group || group.relative_status === "no_variation" || zone.rank == null || zone.result_group_id !== group.result_group_id) return null;
  return `동일 지표 비교 ${group.zone_count}개 동 중 ${zone.rank_tied ? "공동 " : ""}${zone.rank}위`;
}

export function facilityPercentileBand(percentile: number) {
  if (percentile >= FACILITY_PERCENTILE_CUTOFFS.high) return FACILITY_BANDS.high;
  if (percentile >= FACILITY_PERCENTILE_CUTOFFS.middle) return FACILITY_BANDS.middle;
  return FACILITY_BANDS.low;
}

export function zoneDisplayColor(value: number | null, metric: DisplayMetric = "regional_statistics", hasFacilityScore = false): string {
  if (value == null) return metric === "facility_access" && hasFacilityScore ? "#7b519b" : "#64748b";
  if (metric === "facility_access") return facilityPercentileBand(value).color;
  if (value >= 70) return SCORE_COLORS.high;
  if (value >= 40) return SCORE_COLORS.middle;
  return SCORE_COLORS.low;
}
