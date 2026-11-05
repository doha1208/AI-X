import { describe, expect, it } from "vitest";
import { assessmentFixture, environmentRouteFixture } from "@/test/routeFixtures";
import { alternativeAssessment, comparisonAssessment, routeRankingAvailable, routeScore } from "./routeAssessment";
import { guideOptions } from "./routeGuidance";
import { loadHandoff, saveHandoff } from "./guideHandoff";

describe("server route assessment display", () => {
  it.each([[96.77760838437752, "시설 97점"], [0, "시설 0점"]])("displays the returned composite score %s even when the legacy score is null", (score, text) => {
    const display = routeScore({ safety_score: null, environment_model_applied: true, environment_assessment: assessmentFixture({ score: Number(score) }) });
    expect(display.text).toBe(text);
    expect(display.value).toBe(score);
    expect(display.rankable).toBe(true);
  });

  it("keeps a single-factor reference distinct from a composite and does not use a legacy value", () => {
    const display = routeScore({ safety_score: 99, environment_model_applied: true,
      environment_assessment: assessmentFixture({ evaluation_basis: "single_factor", score: null, reference_score: 0, reference_factor: "bell" }) });
    expect(display).toMatchObject({ text: "비상벨 참고 0점", toneValue: null, rankable: false, value: 0 });
  });

  it.each(["partial_coverage", "observed_only", "unavailable"] as const)("does not replace %s evidence with a legacy numeric score", (basis) => {
    const display = routeScore({ safety_score: 99, environment_model_applied: true,
      environment_assessment: assessmentFixture({ score: null, evaluation_basis: basis }) });
    expect(display.value).toBeNull();
    expect(display.rankable).toBe(false);
    expect(display.text).not.toContain("99");
  });

  it("uses the root assessment only for the first candidate, and the comparison only for its own path", () => {
    const response = environmentRouteFixture();
    response.alternatives[0].environment_assessment = null;
    const second = { ...response.alternatives[0], distance_m: 1300 };
    response.alternatives.push(second);
    expect(routeScore(alternativeAssessment(response, response.alternatives[0])).text).toBe("시설 97점");
    expect(routeScore(alternativeAssessment(response, second)).text).toBe("시설 점수 미산정");
    response.comparison_environment_assessment = assessmentFixture({ score: 24.4 });
    expect(routeScore(comparisonAssessment(response)).text).toBe("시설 24점");
  });

  it("does not claim a ranking across different comparison groups", () => {
    const response = environmentRouteFixture();
    expect(routeRankingAvailable(response)).toBe(true);
    response.alternatives.push({ ...response.alternatives[0], environment_assessment: assessmentFixture({ score: 99, comparison_group_id: "different-group" }) });
    expect(routeRankingAvailable(response)).toBe(false);
  });

  it("does not borrow the root assessment when the first candidate has a different path", () => {
    const response = environmentRouteFixture();
    response.alternatives[0].environment_assessment = null;
    response.alternatives[0].route_points = response.route_points.map(point => ({ ...point, lat: point.lat + 0.01 }));
    expect(routeScore(alternativeAssessment(response, response.alternatives[0])).text).toBe("시설 점수 미산정");
    expect(routeRankingAvailable(response)).toBe(false);
  });

  it("preserves the exact assessment through guide option creation and storage", () => {
    const response = environmentRouteFixture();
    const option = guideOptions(response)[0];
    expect(option.environment_assessment).toEqual(response.environment_assessment);
    const end = response.route_points.at(-1)!;
    saveHandoff(end, option);
    expect(loadHandoff(end)?.environment_assessment).toEqual(response.environment_assessment);
    expect(routeScore(loadHandoff(end)!).text).toBe("시설 97점");
  });

  it("retains numeric legacy compatibility only without the environment model", () => {
    expect(routeScore({ safety_score: 0 }).text).toBe("참고 안전지수 0점");
    expect(routeScore({ safety_score: 89, environment_model_applied: true }).text).toBe("시설 점수 미산정");
  });
});
