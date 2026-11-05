import { render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { RouteEnvironmentAssessment, RouteResult, SpotReport } from "@/lib/api";
import ReportPage from "./page";

const routeSafety = vi.fn();
const spotReport = vi.fn();
const nearestSubway = vi.fn();

vi.mock("@/lib/api", () => ({
  routeSafety: (...args: unknown[]) => routeSafety(...args),
  spotReport: (...args: unknown[]) => spotReport(...args),
}));
vi.mock("@/lib/kakao", () => ({ nearestSubway: (...args: unknown[]) => nearestSubway(...args) }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/report",
  useSearchParams: () => new URLSearchParams("at=37.257896,127.029607&atName=테스트집"),
}));
vi.mock("@/lib/useSessionUser", () => ({
  useSessionUser: () => ({ id: 1, email: "test@example.com" }),
  userInitial: () => "테",
}));

function assessment(overrides: Partial<RouteEnvironmentAssessment> = {}): RouteEnvironmentAssessment {
  return {
    model_version: "facility-access-v1", policy_version: "environment-v1-draft", status: "degraded", period: "night",
    distance_m: 1234, score: 82, active_factors: ["cctv", "lighting", "open_store", "bell"],
    used_factors: ["cctv", "bell"], excluded_factors: { open_store: "opening_hours_unverified" },
    factor_coverage: { cctv: 0.64, bell: 1 }, data_factor_availability_ratio: 0.5,
    longest_support_gap_m: null, total_support_gap_m: null, gap_intervals: [], source_versions: {},
    comparison_group_id: "report-test", evaluation_basis: "multi_factor", ...overrides,
  };
}

function result(value: RouteEnvironmentAssessment | null): RouteResult {
  const points = [{ lat: 37.25, lng: 127.03 }, { lat: 37.257896, lng: 127.029607 }];
  return {
    safety_score: null, zones_passed: [], route_points: points, mode: "safety_weighted", period: "night",
    data_disclosure: { data_basis: ["osm_walking_network", "facility_density"], updated_at: null,
      missing_data: [], fallback: { applied: false, mode: "safety_weighted", reason: "none" } },
    alternatives: [{ route_points: points, safety_score: null, distance_m: 1234, zones_passed: [], environment_assessment: value }],
    shortest_route_points: [{ lat: 37.25, lng: 127.03 }, { lat: 37.27, lng: 127.03 }],
    environment_assessment: assessment({ score: 42 }), environment_model_applied: true,
  };
}

beforeEach(() => {
  vi.resetAllMocks();
  nearestSubway.mockResolvedValue({ lat: 37.25, lng: 127.03, name: "테스트역" });
  const report: SpotReport = { lat: 37.257896, lng: 127.029607, period: "day", radius_m: 300, zone: null,
    here_score: null, area_day_score: null, area_night_score: null, counts: null, havens: [],
    area_environment: null, local_environment: null, facility_observations: {}, artifact_version: null,
    status: "pending", unavailable_reason: "facility_artifact_pending" };
  spotReport.mockResolvedValue(report);
});

async function nightWalk() {
  await screen.findByText("테스트역");
  const section = screen.getByRole("heading", { name: "역에서 집까지 밤 귀갓길" }).closest("section");
  expect(section).not.toBeNull();
  return within(section!);
}

it.each([
  ["composite", assessment(), "시설 82점", "추천 경로 시설 평가"],
  ["single factor", assessment({ score: null, evaluation_basis: "single_factor", used_factors: ["bell"],
    reference_score: 68, reference_factor: "bell" }), "비상벨 참고 68점", "밤 귀갓길 시설 평가"],
  ["partial evidence", assessment({ score: null, evaluation_basis: "partial_coverage", used_factors: [],
    score_bounds: { lower: 20, upper: 80 } }), "부분자료 20~80점", "밤 귀갓길 시설 평가"],
  ["unavailable", assessment({ score: null, status: "unavailable", evaluation_basis: "unavailable", used_factors: [] }),
    "점수 미산정", "밤 귀갓길 시설 평가"],
] as const)("renders %s route assessment instead of the retired score", async (_kind, value, text, label) => {
  routeSafety.mockResolvedValue(result(value));
  render(<ReportPage />);
  const walk = await nightWalk();
  expect(walk.getByText(text)).toBeInTheDocument();
  expect(walk.getByText(label)).toBeInTheDocument();
  expect(walk.queryByText("자료 없음")).not.toBeInTheDocument();
  expect(walk.getByText("평가 상세").closest("details")).not.toHaveAttribute("open");
});

it("uses the first alternative's assessment and distance together", async () => {
  routeSafety.mockResolvedValue(result(assessment()));
  render(<ReportPage />);
  const walk = await nightWalk();
  expect(walk.getByText("시설 82점")).toBeInTheDocument();
  expect(walk.queryByText("시설 42점")).not.toBeInTheDocument();
  expect(walk.getByText(/1\.2km · \d+분/)).toBeInTheDocument();
  expect(walk.getByRole("link", { name: "지도에서 경로 보기" })).toHaveAttribute("href", expect.stringContaining("start=37.250000,127.030000"));
});

it("falls back to the top-level assessment when the alternative has none", async () => {
  routeSafety.mockResolvedValue(result(null));
  render(<ReportPage />);
  const walk = await nightWalk();
  expect(walk.getByText("시설 42점")).toBeInTheDocument();
});

it("keeps a known zero score distinct from unavailable data", async () => {
  routeSafety.mockResolvedValue(result(assessment({ score: 0 })));
  render(<ReportPage />);
  const walk = await nightWalk();
  expect(walk.getByText("시설 0점")).toBeInTheDocument();
  expect(walk.queryByText("점수 미산정")).not.toBeInTheDocument();
});

it("labels a longer Tmap route as a general comparison instead of shortest", async () => {
  routeSafety.mockResolvedValue(result(assessment()));
  render(<ReportPage />);
  const walk = await nightWalk();
  expect(walk.getByText("일반 비교 경로")).toBeInTheDocument();
  expect(walk.queryByText("최단 경로")).not.toBeInTheDocument();
});

it("distinguishes a missing station from an unscored walking route", async () => {
  nearestSubway.mockResolvedValue(null);
  render(<ReportPage />);
  expect(await screen.findByText("3km 안에 지하철역이 없어요.")).toBeInTheDocument();
  expect(routeSafety).not.toHaveBeenCalled();
  expect(screen.queryByText("점수 미산정")).not.toBeInTheDocument();
});

it("distinguishes a route request failure from an unscored walking route", async () => {
  routeSafety.mockRejectedValue(new Error("route unavailable"));
  render(<ReportPage />);
  expect(await screen.findByText("귀갓길을 계산하지 못했어요. 잠시 후 다시 시도해주세요.")).toBeInTheDocument();
  expect(screen.queryByText("점수 미산정")).not.toBeInTheDocument();
});

it("uses the new walking area results and labels partial facility counts as observations", async () => {
  spotReport.mockResolvedValue({
    radius_m: 300, zone: null, status: "degraded", area_day_score: 99, havens: [],
    area_environment: {
      day: { ...assessment({ score: 0, period: "day" }), sampled_length_m: 500, reference_at: "2026-11-05T12:00:00+09:00" },
      night: { ...assessment({ score: null, evaluation_basis: "partial_coverage", score_bounds: { lower: 20, upper: 80 } }),
        sampled_length_m: 500, reference_at: "2026-11-05T23:00:00+09:00" },
    },
    facility_observations: { cctv: { count: 2, coverage: "partial", sources: {} } },
  });
  nearestSubway.mockResolvedValue(null);
  render(<ReportPage />);
  const area = await screen.findByRole("heading", { name: "집 주변 300m 보행 시설 접근성" });
  const section = within(area.closest("section")!);
  expect(section.getByText("시설 0점")).toBeInTheDocument();
  expect(section.getByText("부분자료 20~80점")).toBeInTheDocument();
  expect(section.queryByText("99점")).not.toBeInTheDocument();
  expect(section.getByText("확인된 2개")).toBeInTheDocument();
  expect(section.getByText("평가 상세").closest("details")).not.toHaveAttribute("open");
});

it("keeps pending area evaluation separate from point evidence and unverified opening hours", async () => {
  nearestSubway.mockResolvedValue(null);
  spotReport.mockResolvedValue({
    radius_m: 300, zone: null, status: "pending", area_environment: null,
    local_environment: { assessed_at: "2026-11-05T23:00:00+09:00",
      factors: { bell: { state: "present" }, open_store: { state: "unknown" } } },
    havens: [{ kind: "convenience", lat: 37.25, lng: 127.03, distance_m: 55, source_label: "이마트24 매장 찾기",
      opening_status: "unverified", staffing_status: "unverified", operation_status: "not_applicable" }],
  });
  render(<ReportPage />);
  expect(await screen.findByText("주변 보행 평가 자료를 준비 중이에요.")).toBeInTheDocument();
  expect(screen.getByText("가까운 시설 확인")).toBeInTheDocument();
  expect(screen.getByText(/영업 미확인.*유인 미확인/)).toBeInTheDocument();
  expect(screen.queryByText(/24시 편의점/)).not.toBeInTheDocument();
});
