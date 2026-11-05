import { beforeEach, describe, expect, it } from "vitest";
import type { FacilityZone, FacilityZoneAssessment, SafetyZone } from "./api";
import { applyFacilityScoreChanges, applyScoreChanges, loadWatchedZones, MAX_WATCHED_ZONES, toggleWatchedZone } from "./watchedZones";

beforeEach(() => localStorage.clear());

const zone = (code: string, score: number): SafetyZone => ({
  dong_code: code,
  dong_name: `${code}동`,
  lat: 37.5,
  lng: 127.0,
  safety_score: score,
  day_safety_score: score,
  night_safety_score: score,
  period: "day",
});

describe("watchedZones", () => {
  it("toggles a zone on and off", () => {
    expect(toggleWatchedZone(zone("A", 80)).map((z) => z.dong_code)).toEqual(["A"]);
    expect(loadWatchedZones()).toHaveLength(1);
    expect(toggleWatchedZone(zone("A", 80))).toEqual([]);
    expect(loadWatchedZones()).toEqual([]);
  });

  it("refuses to add past the limit, but still lets one be removed", () => {
    for (let i = 0; i < MAX_WATCHED_ZONES; i++) toggleWatchedZone(zone(`Z${i}`, 50));
    expect(toggleWatchedZone(zone("EXTRA", 50))).toHaveLength(MAX_WATCHED_ZONES);
    expect(loadWatchedZones().some((z) => z.dong_code === "EXTRA")).toBe(false);
    expect(toggleWatchedZone(zone("Z0", 50))).toHaveLength(MAX_WATCHED_ZONES - 1);
  });

  it("drops malformed stored entries", () => {
    localStorage.setItem("ansim:watched-zones", JSON.stringify([{ dong_code: "A" }, 3]));
    expect(loadWatchedZones()).toEqual([]);
  });
});

describe("applyScoreChanges", () => {
  it("reports a change in the score the user actually sees, and remembers the new score", () => {
    const watched = [toggleWatchedZone(zone("A", 71.2))[0]];
    const { next, messages } = applyScoreChanges(watched, [zone("A", 64.4)]);

    expect(messages).toEqual(["A동 지역 통계 지수가 71점에서 64점으로 내려갔어요"]);
    expect(next[0].score).toBe(64.4);
  });

  it("stays quiet when the displayed score is unchanged", () => {
    const watched = [toggleWatchedZone(zone("A", 71.2))[0]];
    expect(applyScoreChanges(watched, [zone("A", 70.6)]).messages).toEqual([]);
  });

  it("says raised when the score went up", () => {
    const watched = [toggleWatchedZone(zone("A", 40))[0]];
    expect(applyScoreChanges(watched, [zone("A", 55)]).messages).toEqual(["A동 지역 통계 지수가 40점에서 55점으로 올랐어요"]);
  });

  it("ignores a watched zone that is missing from the latest data", () => {
    const watched = [toggleWatchedZone(zone("A", 71))[0]];
    const { next, messages } = applyScoreChanges(watched, []);
    expect(messages).toEqual([]);
    expect(next).toEqual(watched);
  });
});

const assessment: FacilityZoneAssessment = {
  status: "degraded", evaluation_basis: "multi_factor", score: 70, reference_score: null, reference_factor: null,
  score_bounds: null, sampled_length_m: 100, used_factors: ["bell", "cctv"], factor_coverage: { bell: .6, cctv: .8 },
  factor_evaluation_ratio: {}, verified_distance_ratio: 1, basis_id: "basis", artifact_version: "v1",
  model_version: "model", policy_version: "policy", schedule_key: "weekday-3-day-12", assessed_at: null,
  reference_at: null, unavailable_reason: null,
};

function facility(overrides: Partial<FacilityZoneAssessment> = {}): FacilityZone {
  const { dong_code, dong_name, lat, lng } = zone("A", 99);
  return { dong_code, dong_name, lat, lng, rank: 1, result_group_id: "group", assessment: { ...assessment, ...overrides } };
}

it("reads legacy watches as regional statistics without inventing a saved period", () => {
  localStorage.setItem("ansim:watched-zones", JSON.stringify([{ ...zone("A", 71), score: 71 }]));
  const [saved] = loadWatchedZones();
  expect(saved).toMatchObject({ metric: "regional_statistics", period: null, score: 71 });
  expect(applyScoreChanges([saved], [zone("A", 65)]).messages).toEqual([]);
});

it.each(["basis_id", "model_version", "policy_version", "schedule_key"] as const)(
  "silently establishes a new baseline when %s changes",
  field => {
    const saved = toggleWatchedZone(facility(), "facility_access", "day");
    const { next, messages } = applyFacilityScoreChanges(saved, [facility({ [field]: "new", score: 80, artifact_version: "v2" })], "day");
    expect(messages).toEqual([]);
    expect(next[0]).toMatchObject({ [field]: "new", score: 80, artifact_version: "v2" });
  },
);

it("reports a changed displayed facility score only for new data with the same comparison meaning", () => {
  const saved = toggleWatchedZone(facility(), "facility_access", "day");
  expect(applyScoreChanges(saved, [zone("A", 99)]).next).toEqual(saved);
  expect(applyFacilityScoreChanges(saved, [facility({ score: 80 })], "day").messages).toEqual([]);
  expect(applyFacilityScoreChanges(saved, [facility({ score: 80, artifact_version: "v2" })], "night").messages).toEqual([]);
  const next = applyFacilityScoreChanges(saved, [facility({ score: 80, artifact_version: "v2" })], "day");
  expect(next.messages).toEqual(["A동 공개 자료 기준 시설 점수가 70점에서 80점으로 바뀌었어요"]);
  expect(JSON.parse(localStorage.getItem("ansim:watched-zones")!).schema).toBe(2);
});
