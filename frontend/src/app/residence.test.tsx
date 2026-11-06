import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { FacilityBasisGroup, FacilityZoneAssessment, FacilityZoneResponse } from "@/lib/api";
import { residenceZoneDisplay, zoneDisplayColor, type DisplayZone } from "@/lib/zoneDisplay";
import type { DisplayMetric } from "@/lib/api";
import Residence from "./page";

const load = vi.fn();
vi.mock("@/lib/api", async importOriginal => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  residenceRecommend: async () => [{ dong_code: "A", dong_name: "가동", lat: 37.5, lng: 127, safety_score: 95, period: "day" }],
  nearbyZones: async () => [],
  nearbyBells: async () => [],
  facilityZones: (...args: unknown[]) => load(...args),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/", useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/useSessionUser", () => ({ useSessionUser: () => ({ id: 1, email: "test@example.invalid" }), userInitial: () => "T" }));
vi.mock("@/lib/useMyLocation", () => ({ useMyLocation: () => ({ location: { lat: 37.5, lng: 127 }, request: vi.fn() }) }));
vi.mock("@/components/SafetyMap", () => ({
  SafetyMap: ({ zones, displayMetric, facilityGroup }: {
    zones: DisplayZone[]; displayMetric: DisplayMetric; facilityGroup?: FacilityBasisGroup;
  }) => (
    <div data-testid="test-map">{zones.map(zone => {
      const display = residenceZoneDisplay(zone, displayMetric, facilityGroup);
      return <span key={zone.dong_code} data-testid={`map-${zone.dong_code}`}
        data-color={zoneDisplayColor(display.value, displayMetric, display.hasFacilityScore)}>{display.text}</span>;
    })}</div>
  ),
}));

const assessment: FacilityZoneAssessment = {
  status: "degraded", evaluation_basis: "multi_factor", score: 70, reference_score: null, reference_factor: null,
  score_bounds: null, sampled_length_m: 300, used_factors: ["bell", "cctv"], factor_coverage: { bell: .6, cctv: .8 },
  factor_evaluation_ratio: {}, verified_distance_ratio: 1, basis_id: "group", artifact_version: "v1",
  model_version: "model", policy_version: "policy", schedule_key: "thursday", assessed_at: null,
  reference_at: null, unavailable_reason: null,
};

const report: FacilityZoneResponse = {
    status: "available", period: "day", weekday: 3, reference_hour: 12, basis_id: "group", artifact_version: "v1",
    groups: [{ basis_id: "group", result_group_id: "result", used_factors: ["bell", "cctv"], zone_count: 1 }],
    comparison: null,
    zones: [
      { dong_code: "A", dong_name: "가동", lat: 37.5, lng: 127, rank: 1, result_group_id: "result", assessment },
      { dong_code: "B", dong_name: "나동", lat: 37.5, lng: 127, rank: null, result_group_id: "other", assessment: { ...assessment, score: 90, basis_id: "other" } },
      { dong_code: "C", dong_name: "다동", lat: 37.5, lng: 127, rank: null, result_group_id: null,
        assessment: { ...assessment, evaluation_basis: "single_factor", score: null, reference_score: 80, reference_factor: "bell" } },
    ],
};

it("distinguishes confirmed raw scores from unranked references when the old group is too small", async () => {
  localStorage.clear();
  load.mockResolvedValue(report);
  render(<Residence />);
  expect(await screen.findByTestId("map-A")).toHaveTextContent("95점");
  fireEvent.change(screen.getByLabelText("평가 기준"), { target: { value: "facility_access" } });
  const mapA = await screen.findByTestId("map-A");
  expect(mapA).toHaveTextContent("인접 비율 평균 70%");
  expect(mapA).toHaveAttribute("data-color", "#7b519b");
  expect(screen.queryByText("집단 내 상대 위치")).not.toBeInTheDocument();
  const other = screen.getByRole("button", { name: /나동.*다른 지표 집단/ });
  expect(within(other).getByLabelText("순위 없음")).toBeInTheDocument();
  const reference = screen.getByRole("button", { name: /다동.*비상벨 참고 80점/ });
  expect(within(reference).getByLabelText("순위 없음")).toBeInTheDocument();
  expect(screen.getByTestId("map-C")).toHaveAttribute("data-color", "#64748b");
  expect(screen.getByLabelText("동일 지표 비교 1개 동 중 1위")).toBeInTheDocument();
});

it("restores map colors from a complete group of ranks on an older API", async () => {
  localStorage.clear();
  const group = Array.from({ length: 20 }, (_, index) => ({
    ...report.zones[0],
    dong_code: index === 0 ? "A" : `legacy-${index}`,
    dong_name: index === 0 ? "가동" : `시험 ${index}동`,
    rank: index < 2 ? 1 : 3,
    assessment: index < 2 ? assessment : { ...assessment, score: 10 },
  }));
  load.mockResolvedValue({
    ...report,
    groups: [{ ...report.groups[0], zone_count: 20 }],
    zones: [...group, ...report.zones.slice(1)],
  } satisfies FacilityZoneResponse);
  render(<Residence />);
  fireEvent.change(screen.getByLabelText("평가 기준"), { target: { value: "facility_access" } });
  const row = await screen.findByRole("button", { name: /가동.*백분위 95\.0/ });
  expect(within(row).getByLabelText("동일 지표 비교 20개 동 중 공동 1위")).toBeInTheDocument();
  expect(screen.getByTestId("map-A")).toHaveAttribute("data-color", "#2e7d32");
  expect(screen.getByTestId("map-legacy-2")).toHaveTextContent("백분위 45.0");
  expect(screen.getByTestId("map-legacy-2")).toHaveAttribute("data-color", "#f9a825");
  expect(screen.getByTestId("map-B")).toHaveAttribute("data-color", "#7b519b");
  expect(screen.getByTestId("map-C")).toHaveAttribute("data-color", "#64748b");
});

it("shows the same percentile in the list, on the map and in the selected detail", async () => {
  localStorage.clear();
  load.mockResolvedValue({
    ...report,
    relative_method: "midrank-percentile-v1",
    groups: [{ ...report.groups[0], zone_count: 100, relative_status: "available" }],
    zones: [
      { ...report.zones[0], rank: 27, rank_tied: true, relative_percentile: 72,
        assessment: { ...assessment, score: 18, factor_coverage: { bell: .16, cctv: .20 } } },
      ...report.zones.slice(1),
    ],
  } satisfies FacilityZoneResponse);
  render(<Residence />);
  fireEvent.change(screen.getByLabelText("평가 기준"), { target: { value: "facility_access" } });
  const row = await screen.findByRole("button", { name: /가동.*백분위 72\.0/ });
  expect(within(row).getByLabelText("동일 지표 비교 100개 동 중 공동 27위")).toBeInTheDocument();
  expect(screen.getByTestId("map-A")).toHaveTextContent("백분위 72.0");
  expect(screen.getByTestId("map-A")).toHaveAttribute("data-color", "#2e7d32");
  expect(screen.getByTestId("map-B")).toHaveAttribute("data-color", "#7b519b");
  expect(screen.getByText("집단 내 상대 위치")).toBeInTheDocument();
  expect(screen.getByText("상위권 (백분위 60 이상)")).toBeInTheDocument();
  expect(screen.getByText("중간권 (백분위 10 이상 60 미만)")).toBeInTheDocument();
  expect(screen.getByText("하위권 (백분위 10 미만)")).toBeInTheDocument();
  fireEvent.click(row);
  const detail = screen.getByRole("region", { name: "선택 안전구역 상세" });
  expect(within(detail).getByText("백분위 72.0")).toBeInTheDocument();
  fireEvent.click(within(detail).getByText("평가 상세"));
  expect(within(detail).getByText("지표별 시설 인접 비율 평균 18%")).toBeVisible();
  expect(within(detail).getByText(/비상벨 16%/)).toBeVisible();
});

it("hides relative ranking emphasis when all displayed values tie", async () => {
  localStorage.clear();
  load.mockResolvedValue({
    ...report,
    relative_method: "midrank-percentile-v1",
    groups: [{ ...report.groups[0], zone_count: 20, relative_status: "no_variation" }],
    zones: [{ ...report.zones[0], rank_tied: true, relative_percentile: null }],
  } satisfies FacilityZoneResponse);
  render(<Residence />);
  fireEvent.change(screen.getByLabelText("평가 기준"), { target: { value: "facility_access" } });
  const row = await screen.findByRole("button", { name: /가동.*인접 비율 평균 70%/ });
  expect(within(row).getByLabelText("순위 없음")).toBeInTheDocument();
  expect(screen.getByText("집단 내 점수 차이 없음")).toBeInTheDocument();
  expect(screen.queryByText("집단 내 상대 위치")).not.toBeInTheDocument();
});

it("keeps the full-group percentile nearby and clears it while a different time slot loads", async () => {
  localStorage.clear();
  const day: FacilityZoneResponse = {
    ...report,
    relative_method: "midrank-percentile-v1",
    groups: [{ ...report.groups[0], zone_count: 20, relative_status: "available" }],
    zones: [{ ...report.zones[0], relative_percentile: 60 }, { ...report.zones[1], lat: 37.7 }],
  };
  const night = {
    ...day,
    period: "night",
    reference_hour: 23,
    zones: [{ ...day.zones[0], relative_percentile: 9.9 }],
  } satisfies FacilityZoneResponse;
  let resolveNight: (response: FacilityZoneResponse) => void = () => {};
  load.mockImplementation(({ period }) => period === "night"
    ? new Promise<FacilityZoneResponse>(resolve => { resolveNight = resolve; })
    : Promise.resolve(day));
  render(<Residence />);
  fireEvent.change(screen.getByLabelText("평가 기준"), { target: { value: "facility_access" } });
  expect(await screen.findByRole("button", { name: /나동.*다른 지표 집단/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "내 주변 순위 보기" }));
  await screen.findByRole("button", { name: "전체 지역 순위 보기" });
  expect(screen.queryByRole("button", { name: /나동.*다른 지표 집단/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /가동.*백분위 60\.0/ })).toBeInTheDocument();
  expect(screen.getByTestId("map-A")).toHaveAttribute("data-color", "#2e7d32");

  fireEvent.change(screen.getByLabelText("대표 시각"), { target: { value: "night" } });
  expect(screen.queryByText("백분위 60.0")).not.toBeInTheDocument();
  await act(async () => resolveNight(night));
  expect(await screen.findByRole("button", { name: /가동.*백분위 9\.9/ })).toBeInTheDocument();
  expect(screen.getByTestId("map-A")).toHaveAttribute("data-color", "#c62828");
});
