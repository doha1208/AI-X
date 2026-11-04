import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RouteEnvironmentDetails, RouteEnvironmentSummary } from "@/components/RouteEnvironmentSummary";
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
    expect(screen.getByText(/점수 미산정/)).toBeInTheDocument();
  });
  it("keeps the score visible without expanding evidence in a route card", () => {
    render(<RouteEnvironmentSummary assessment={assessment} />);
    expect(screen.getByText("시설 72점")).toBeInTheDocument();
    expect(screen.queryByText(/최장 시설 공백|사용 지표|평가 제외/)).not.toBeInTheDocument();
    expect(screen.queryByText(/주의 구역/)).not.toBeInTheDocument();
  });
  it("opens evidence on demand and explains that excluded data is not an absent facility", () => {
    render(<RouteEnvironmentDetails assessment={assessment} />);
    const toggle = screen.getByText("평가 상세");
    expect(toggle.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText(/최장 시설 공백 160m/)).not.toBeVisible();
    fireEvent.click(toggle);
    expect(toggle.closest("details")).toHaveAttribute("open");
    expect(screen.getByText(/최장 시설 공백 160m/)).toBeVisible();
    expect(screen.getByText(/사용 지표 2\/4/)).toBeVisible();
    expect(screen.getByText(/시설이 없다는 뜻은 아니/)).toBeVisible();
  });
  it("does not turn unavailable data into zero or a legacy dong score", () => {
    render(<RouteEnvironmentSummary assessment={null} />);
    expect(screen.getByText("점수 미산정")).toBeInTheDocument();
    expect(screen.queryByText(/0점/)).not.toBeInTheDocument();
  });
  it("distinguishes observed facilities from missing verification and opening hours", () => {
    render(<RouteEnvironmentDetails assessment={{ ...assessment, score: null, used_factors: [],
      observed_facility_counts: { bell: 12, cctv: 5, store: 8 },
      excluded_factors: { bell: "provenance_unverified", open_store: "opening_hours_unverified" } }} />);
    fireEvent.click(screen.getByText("평가 상세"));
    expect(screen.getByText(/비상벨 12개/)).toBeVisible();
    expect(screen.getByText(/원본 출처와 기준일/)).toBeVisible();
    expect(screen.getByText(/시간별 영업 근거/)).toBeVisible();
    expect(screen.queryByText(/시설 0점/)).not.toBeInTheDocument();
  });
  it("choice cards ignore low dong scores and use the environment assessment", () => {
    const option = { kind: "safe" as const, points: [{ lat: 37.5, lng: 127 }, { lat: 37.51, lng: 127 }], distanceM: 1000,
      zones: [{ dong_code: "test", dong_name: "test", lat: 37.5, lng: 127, safety_score: 10, day_safety_score: 10, night_safety_score: 10, period: "night" as const }],
      environmentAssessment: assessment };
    const comparison = { ...option, kind: "shortest" as const };
    render(<ChoicePanel destination={null} choice={{ options: [option, comparison], safetyWeighted: true, period: "night" }} safeOption={option}
      previewOption={option} myLocation={undefined} routeError={null} onPreview={() => {}} onChoose={() => {}} onRetry={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("시설 72점")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /최단 경로|일반 도보 경로/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/지나는 동 평균|주의 구역/)).not.toBeInTheDocument();
  });
});
