import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouteEnvironmentSummary } from "@/components/RouteEnvironmentSummary";
import { ChoicePanel } from "./ChoicePanel";
import type { RouteEnvironmentAssessment } from "@/lib/api";
import { environmentPeekText } from "@/lib/routeGuidance";
import { RoutePeek } from "@/components/RoutePeek";

const assessment = {
  model_version: "facility-access-v1", policy_version: "environment-v1-draft", status: "degraded", period: "night",
  distance_m: 1000, score: 72, active_factors: ["cctv", "lighting", "open_store", "bell"], used_factors: ["lighting", "open_store"],
  excluded_factors: { cctv: "verified_complete_coverage_required", bell: "verified_complete_coverage_required" },
  factor_coverage: { lighting: 0.7, open_store: 0.74 }, data_factor_availability_ratio: 0.5,
  longest_support_gap_m: 160, total_support_gap_m: 200, gap_intervals: [], source_versions: {}, comparison_group_id: "group",
} satisfies RouteEnvironmentAssessment;

describe("route environment presentation", () => {
  it("labels facility scores and missing evidence in the initially collapsed mobile choices", () => {
    render(<RoutePeek items={[
      {key:"a",label:"추천",minutes:10,distance:"670m",score:environmentPeekText(assessment),active:true},
      {key:"b",label:"일반",minutes:10,distance:"670m",score:environmentPeekText(null),active:false},
    ]} onSelect={() => {}} onStart={() => {}} />);
    expect(screen.getByText(/시설 72점/)).toBeInTheDocument();
    expect(screen.getByText(/시설 평가 데이터 부족/)).toBeInTheDocument();
  });
  it("shows facility evidence and longest gap without a crime safety grade", () => {
    render(<RouteEnvironmentSummary assessment={assessment} />);
    expect(screen.getByText(/시설 접근성 지수 72점/)).toBeInTheDocument();
    expect(screen.getByText(/최장 시설 공백 160m/)).toBeInTheDocument();
    expect(screen.getByText(/사용 지표 2\/4/)).toBeInTheDocument();
    expect(screen.queryByText(/주의 구역/)).not.toBeInTheDocument();
  });
  it("does not turn unavailable data into zero or a legacy dong score", () => {
    render(<RouteEnvironmentSummary assessment={null} />);
    expect(screen.getByText("시설 평가 데이터 부족")).toBeInTheDocument();
    expect(screen.queryByText(/0점/)).not.toBeInTheDocument();
  });
  it("choice cards ignore low dong scores and use the environment assessment", () => {
    const option = { kind: "safe" as const, points: [{ lat: 37.5, lng: 127 }, { lat: 37.51, lng: 127 }], distanceM: 1000,
      zones: [{ dong_code: "test", dong_name: "test", lat: 37.5, lng: 127, safety_score: 10, day_safety_score: 10, night_safety_score: 10, period: "night" as const }],
      environmentAssessment: assessment };
    render(<ChoicePanel destination={null} choice={{ options: [option], safetyWeighted: true, period: "night" }} safeOption={option}
      previewOption={option} myLocation={undefined} routeError={null} onPreview={() => {}} onChoose={() => {}} onRetry={() => {}} onCancel={() => {}} />);
    expect(screen.getByText(/시설 접근성 지수 72점/)).toBeInTheDocument();
    expect(screen.queryByText(/지나는 동 평균|주의 구역/)).not.toBeInTheDocument();
  });
});
