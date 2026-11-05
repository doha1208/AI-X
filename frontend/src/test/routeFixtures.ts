import type { RouteEnvironmentAssessment, RouteResult } from "@/lib/api";

export function assessmentFixture(overrides: Partial<RouteEnvironmentAssessment> = {}): RouteEnvironmentAssessment {
  return {
    model_version: "facility-access-v1", policy_version: "environment-v1-draft", status: "degraded",
    period: "day", distance_m: 1200, score: 96.77760838437752,
    active_factors: ["cctv", "open_store", "bell"], used_factors: ["bell", "cctv"],
    excluded_factors: { open_store: "opening_hours_unverified" }, factor_coverage: { bell: 1, cctv: 0.9355 },
    data_factor_availability_ratio: 2 / 3, longest_support_gap_m: null, total_support_gap_m: null,
    gap_intervals: [], source_versions: {}, comparison_group_id: "same-evaluation-group",
    evaluation_basis: "multi_factor", reference_score: null, reference_factor: null, score_bounds: null,
    observed_facility_counts: { bell: 49, cctv: 23 }, factor_evaluation_ratio: { bell: 1, cctv: 1 },
    verified_distance_ratio: 1, evidence_factors: ["bell", "cctv"], ...overrides,
  };
}

export function environmentRouteFixture(): RouteResult {
  const assessment = assessmentFixture();
  const points = [{ lat: 37.302, lng: 126.866 }, { lat: 37.31, lng: 126.87 }];
  return {
    safety_score: null, zones_passed: [], route_points: points, mode: "safety_weighted", period: "day",
    data_disclosure: { data_basis: ["osm_walking_network", "facility_density"], updated_at: null, missing_data: [],
      fallback: { applied: false, mode: "safety_weighted", reason: "none" } },
    alternatives: [{ route_points: points, safety_score: null, distance_m: 1200, zones_passed: [], environment_assessment: assessment }],
    shortest_route_points: null, shortest_zones_passed: null,
    environment_model_applied: true, environment_assessment: assessment, comparison_environment_assessment: null,
  };
}
