import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { LiveFacilityReport, SafeHaven } from "@/lib/api";
import { LiveFacilityDetails, SafetyAlerts } from "./SafetyAlerts";

const actions = { onSnooze: vi.fn(), onNotifyGuardians: vi.fn() };
const shop: SafeHaven = {
  kind: "convenience", lat: 37.5, lng: 127, distance_m: 50,
  source_id: "shop", source_label: "공개 매장 자료", source_url: null, source_version: "one",
  opening_status: "unverified", schedule_status: "published_schedule",
  staffing_status: "unverified", operation_status: "not_applicable",
};

it("renders a lighting-only gap without claiming a store is open or staffed", () => {
  render(<SafetyAlerts facilityAlert={{ id: "one", contextId: "version", kind: "lighting", startM: 0, endM: 140 }}
    haven={shop} overdue={false} {...actions} />);
  expect(screen.getByRole("status")).toHaveTextContent("보안등 접근 공백");
  expect(screen.getByRole("status")).not.toHaveTextContent("조명·영업 시설 접근 공백");
  expect(screen.getByText(/영업 미확인.*유인 미확인/)).toBeInTheDocument();
  expect(screen.queryByText(/24시 편의점/)).not.toBeInTheDocument();
});

it("keeps missing evidence neutral and arrival checks independent", () => {
  render(<><SafetyAlerts facilityAlert={null} haven={null} overdue {...actions} />
    <LiveFacilityDetails report={null} /></>);
  expect(screen.getByRole("alert")).toHaveTextContent("예상 도착 시간");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getByText("현재 시각의 시설 근거를 확인하지 못했어요.")).toBeInTheDocument();
});

it("shows daytime CCTV evidence without a lighting warning", () => {
  const evaluated_at = "2026-11-05T12:00:00+09:00";
  const daytime: LiveFacilityReport = {
    assessment: null, havens: [], route_evidence: {}, artifact_version: "one", period: "day", status: "degraded",
    temporal_key: "day", evaluated_at, valid_until: "2026-11-05T12:01:00+09:00",
    local_environment: { period: "day", point: [37.5, 127], artifact_version: "one",
      model_version: "facility-access-v1", policy_version: "test", assessed_at: evaluated_at, source_versions: {},
      factors: { cctv: { state: "present", comparison_present: true, comparison_known: true, observed_present: true } } },
  };
  render(<LiveFacilityDetails report={daytime} />);
  expect(screen.getByText("CCTV: 인접 근거 있음")).toBeInTheDocument();
  expect(screen.queryByText(/보안등 접근 공백/)).not.toBeInTheDocument();
});
