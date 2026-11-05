import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DataSourcesPage from "./page";
import MyInfoPage from "../me/page";
import ScoringAdminPage from "../admin/scoring/page";

vi.mock("@/lib/useSessionUser", () => ({ useSessionUser: () => ({ email: "test@example.com" }), userInitial: () => "T" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/data" }));
vi.mock("@/lib/auth", () => ({ getSessionUser: vi.fn().mockResolvedValue({ email: "test@example.com" }), endSession: vi.fn() }));
vi.mock("@/lib/api", () => ({
  listScoringProfiles: vi.fn().mockResolvedValue([]), listScoreBuilds: vi.fn().mockResolvedValue([]),
  createScoringProfileDraft: vi.fn(), applyScoringProfile: vi.fn(),
  assessmentStatus: vi.fn().mockResolvedValue({
    route_artifact: { available: true, version: "artifact-test", area_environment_ready: true, zone_environment_ready: false },
    facility_assessment: { model_version: "facility-access-v1", policy_version: "environment-v1-draft", artifact_version: "artifact-test", applied: true },
  }),
}));
afterEach(cleanup);

it.each([["data", DataSourcesPage], ["me", MyInfoPage]] as const)("%s distinguishes regional statistics, facilities and live alerts", (_, Page) => {
  render(<Page />);
  expect(screen.getAllByText(/지역 통계 지수/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/보행 시설 접근성/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/walking-gap-v1/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/environment-v1-draft/).length).toBeGreaterThan(0);
  expect(document.body.textContent).not.toMatch(/밤에는 편의점만 가점|밤에 근처 길은 감점|공원·하천변을 덜 좋게/);
  expect(document.body.textContent).toContain("영업·유인·작동 상태");
});

it("labels collection date separately and keeps raw park/nightlife data outside the facility score", () => {
  render(<DataSourcesPage />);
  expect(screen.getAllByText(/2026-11-04/).length).toBeGreaterThan(0);
  expect(screen.getByText(/2020-01-01~2026-06-01/)).toBeInTheDocument();
  expect(screen.getByText(/원자료를 보존하며 새 시설 점수에는 사용하지/)).toBeInTheDocument();
  expect(screen.getByText(/현실의 모든 골목/)).toBeInTheDocument();
});

it("admin weights control regional statistics and separately show deployed facility policy and readiness", async () => {
  render(<ScoringAdminPage />);
  expect(screen.getByRole("heading", { name: "지역 통계 지수 프로필 관리" })).toBeInTheDocument();
  expect(await screen.findByText(/artifact-test/)).toBeInTheDocument();
  expect(screen.getByText(/주변 평가 준비 · 동별 평가 준비 중/)).toBeInTheDocument();
  expect(screen.getByText(/시설 반경·동일 비중 계산·실시간 알림 임계값은 변경하지/)).toBeInTheDocument();
});
