import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { FacilityZoneAssessment, FacilityZoneResponse } from "@/lib/api";
import { zoneDisplay, zoneDisplayColor, type DisplayZone } from "@/lib/zoneDisplay";
import type { DisplayMetric } from "@/lib/api";
import Residence from "./page";

const load = vi.fn();
vi.mock("@/lib/api", async importOriginal => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  residenceRecommend: async () => [{ dong_code: "A", dong_name: "가동", lat: 37.5, lng: 127, safety_score: 95, period: "day" }],
  facilityZones: (...args: unknown[]) => load(...args),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/", useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/useSessionUser", () => ({ useSessionUser: () => ({ id: 1, email: "test@example.invalid" }), userInitial: () => "T" }));
vi.mock("@/lib/useMyLocation", () => ({ useMyLocation: () => ({ location: null, request: vi.fn() }) }));
vi.mock("@/components/SafetyMap", () => ({
  SafetyMap: ({ zones, displayMetric }: { zones: DisplayZone[]; displayMetric: DisplayMetric }) => (
    <div data-testid="test-map">{zones.map(zone => {
      const display = zoneDisplay(zone, displayMetric);
      return <span key={zone.dong_code} data-testid={`map-${zone.dong_code}`} data-color={zoneDisplayColor(display.value)}>{display.text}</span>;
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

it("switches cards and map together, preserving other groups and neutral reference rows without ranks", async () => {
  localStorage.clear();
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
  load.mockResolvedValue(report);
  render(<Residence />);
  expect(await screen.findByTestId("map-A")).toHaveTextContent("95점");
  fireEvent.change(screen.getByLabelText("평가 기준"), { target: { value: "facility_access" } });
  const mapA = await screen.findByTestId("map-A");
  expect(mapA).toHaveTextContent("시설 70점");
  const other = screen.getByRole("button", { name: /나동.*시설 90점/ });
  expect(within(other).getByLabelText("순위 없음")).toBeInTheDocument();
  const reference = screen.getByRole("button", { name: /다동.*비상벨 참고 80점/ });
  expect(within(reference).getByLabelText("순위 없음")).toBeInTheDocument();
  expect(screen.getByTestId("map-C")).toHaveAttribute("data-color", "#64748b");
  expect(screen.getByLabelText("동일 지표 비교 1개 동 중 1위")).toBeInTheDocument();
});
