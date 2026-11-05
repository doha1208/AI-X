import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError, type FacilityZoneAssessment, type FacilityZoneResponse } from "@/lib/api";
import Compare from "./page";

const load = vi.fn();
let query = "";
vi.mock("@/lib/api", async importOriginal => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  facilityZones: (...args: unknown[]) => load(...args),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/compare", useSearchParams: () => new URLSearchParams(query),
}));
vi.mock("@/lib/useSessionUser", () => ({ useSessionUser: () => ({ id: 1, email: "test@example.invalid" }), userInitial: () => "T" }));

const assessment: FacilityZoneAssessment = {
  status: "degraded", evaluation_basis: "multi_factor", score: 90, reference_score: null, reference_factor: null,
  score_bounds: null, sampled_length_m: 300, used_factors: ["bell", "cctv"], factor_coverage: { bell: .8, cctv: 1 },
  factor_evaluation_ratio: {}, verified_distance_ratio: 1, basis_id: "current", artifact_version: "v1",
  model_version: "model", policy_version: "policy", schedule_key: "thursday", assessed_at: null, reference_at: null, unavailable_reason: null,
};
const response: FacilityZoneResponse = {
  status: "available", period: "day", weekday: 3, reference_hour: 12, basis_id: "current", artifact_version: "v1",
  groups: [{ basis_id: "current", result_group_id: "id", used_factors: ["bell", "cctv"], zone_count: 1 }],
  zones: [
    { dong_code: "A", dong_name: "가동", lat: 37.5, lng: 127, rank: 1, result_group_id: "id", assessment },
    { dong_code: "B", dong_name: "나동", lat: 37.5, lng: 127, rank: null, result_group_id: null,
      assessment: { ...assessment, score: 70, used_factors: ["lighting", "open_store"], factor_coverage: { lighting: .7, open_store: .7 } } },
  ],
  comparison: { dong_codes: ["A", "B"], used_factors: [], scores: {}, evaluation_basis: "not_comparable" },
};

beforeEach(() => {
  query = "metric=facility_access&period=day";
  load.mockReset();
  localStorage.setItem("ansim:watched-zones", JSON.stringify(response.zones.map(zone => ({
    dong_code: zone.dong_code, dong_name: zone.dong_name, lat: zone.lat, lng: zone.lng, score: 88,
  }))));
});

it("does not highlight a winner across different individual facility criteria", async () => {
  load.mockResolvedValue(response);
  render(<Compare />);
  expect(await screen.findByText(/공통으로 확인된 지표가 없어/)).toBeInTheDocument();
  expect(screen.getByText("시설 90점").closest("td")).not.toHaveAttribute("class");
  expect(screen.queryByText("공통 지표 점수")).not.toBeInTheDocument();
});

it("requires explicit reselection for an expired basis and shows a single-factor comparison distinctly", async () => {
  query += "&basis=old";
  load.mockRejectedValueOnce(new ApiError("현재 적용할 비교 기준을 다시 선택해 주세요.", 409, {
    reason: "comparison_basis_changed", groups: response.groups,
  })).mockResolvedValueOnce({
    ...response, comparison: { dong_codes: ["A", "B"], used_factors: ["bell"], scores: { A: 80, B: 40 }, evaluation_basis: "single_factor" },
  });
  render(<Compare />);
  expect(await screen.findByRole("alert")).toHaveTextContent("다시 선택해 주세요");
  expect(load).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText("순위 비교 집합"), { target: { value: "current" } });
  expect(await screen.findByText("공통 지표 참고 비율")).toBeInTheDocument();
  expect(load.mock.calls[1][0]).toMatchObject({ basisId: "current", period: "day", codes: ["A", "B"] });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
