import { expect, it } from "vitest";
import type { FacilityZoneAssessment } from "./api";
import { facilityPercentileBand, zoneDisplay, zoneDisplayColor } from "./zoneDisplay";

const base = { dong_code: "A", dong_name: "A동", lat: 37.5, lng: 127, safety_score: 99 };
const assessment: FacilityZoneAssessment = {
  status: "degraded", evaluation_basis: "single_factor", score: null, reference_score: 80, reference_factor: "bell",
  score_bounds: null, sampled_length_m: 100, used_factors: ["bell"], factor_coverage: { bell: .8 },
  factor_evaluation_ratio: {}, verified_distance_ratio: 1, basis_id: "basis", artifact_version: "artifact",
  model_version: "model", policy_version: "policy", schedule_key: "day", assessed_at: null,
  reference_at: null, unavailable_reason: null,
};

it("preserves regional values and gives a single-factor facility value neutral map styling", () => {
  const zone = { ...base, assessment };
  expect(zoneDisplay(zone, "regional_statistics")).toEqual({ value: 99, text: "99점" });
  const facility = zoneDisplay(zone, "facility_access");
  expect(facility).toEqual({ value: null, text: "비상벨 참고 80점" });
  expect(zoneDisplayColor(facility.value)).toBe("#64748b");
});

it("shows verified zero, partial bounds and missing boundaries without substituting a regional score", () => {
  expect(zoneDisplay({ ...base, assessment: { ...assessment, evaluation_basis: "multi_factor", score: 0 } }, "facility_access"))
    .toEqual({ value: 0, text: "시설 0점" });
  expect(zoneDisplay({ ...base, assessment: { ...assessment, evaluation_basis: "partial_coverage", score_bounds: { lower: 20.1, upper: 80.1 } } }, "facility_access"))
    .toEqual({ value: null, text: "부분자료 20~81점" });
  expect(zoneDisplay({ ...base, assessment: { ...assessment, evaluation_basis: "unavailable", unavailable_reason: "boundary_missing" } }, "facility_access"))
    .toEqual({ value: null, text: "경계 자료 미확인" });
});

it.each([
  [9.9, "하위권", "#c62828"],
  [10, "중간권", "#f9a825"],
  [59.9, "중간권", "#f9a825"],
  [60, "상위권", "#2e7d32"],
] as const)("shows facility percentile %s as %s", (percentile, text, color) => {
  expect(facilityPercentileBand(percentile).text).toBe(text);
  expect(zoneDisplayColor(percentile, "facility_access")).toBe(color);
});
