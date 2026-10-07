import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RoutePage from "./page";

const routeSafety = vi.fn();

vi.mock("@/lib/api", () => ({
  routeSafety: (...args: unknown[]) => routeSafety(...args),
  getRouteHistory: vi.fn().mockResolvedValue({ rememberRouteHistory: true, items: [] }),
  saveRouteHistory: vi.fn().mockResolvedValue(undefined),
  setRouteHistoryRemember: vi.fn(),
  clearRouteHistory: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/route",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/useSessionUser", () => ({
  useSessionUser: () => ({ name: "테스트 사용자", email: "test@example.com" }),
  userInitial: () => "테",
}));

vi.mock("@/lib/useMyLocation", () => ({
  useMyLocation: () => ({ location: null, request: vi.fn() }),
}));

vi.mock("@/lib/useRouteBells", () => ({ useRouteBells: () => [] }));

vi.mock("@/components/SafetyMap", async () => {
  const React = await import("react");
  return {
    SafetyMap: React.forwardRef(function MockSafetyMap() {
      return <div data-testid="safety-map" />;
    }),
  };
});

describe("RoutePage responsive presentation", () => {
  it("keeps one map and exposes route results through the adaptive sheet", () => {
    render(<RoutePage />);

    expect(screen.getAllByTestId("safety-map")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "경로 결과 펼치기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "출발지와 도착지 바꾸기" })).toBeInTheDocument();
  });

  it("clears the previous route when a replacement search fails", async () => {
    routeSafety
      .mockResolvedValueOnce({
        safety_score: 55,
        zones_passed: [],
        route_points: [{ lat: 37.532, lng: 126.99 }, { lat: 37.548, lng: 127.01 }],
        mode: "straight_line",
        period: "day",
        data_disclosure: {
          data_basis: ["straight_line_estimate", "zone_safety_indicators"],
          updated_at: null,
          missing_data: [{ factor: "crime_rate", affected_zone_count: 1 }],
          fallback: { applied: true, mode: "straight_line", reason: "tmap_unavailable" },
        },
        alternatives: [{
          route_points: [{ lat: 37.532, lng: 126.99 }, { lat: 37.548, lng: 127.01 }],
          safety_score: 55,
          distance_m: 2500,
          zones_passed: [],
        }],
        shortest_route_points: null,
        shortest_zones_passed: null,
      })
      .mockRejectedValueOnce(new Error("직선거리 10km를 초과하는 보행 경로는 지원하지 않습니다"));

    render(<RoutePage />);
    const start = screen.getByLabelText("출발지 주소");
    const end = screen.getByLabelText("도착지 주소");
    const search = screen.getByRole("button", { name: "추천 경로 찾기" });

    fireEvent.change(start, { target: { value: "37.532, 126.990" } });
    fireEvent.change(end, { target: { value: "37.548, 127.010" } });
    fireEvent.click(search);
    expect(await screen.findByLabelText("경로 검색 결과")).toBeInTheDocument();
    expect(screen.getByText("공개 데이터 기반 참고 정보이며, 실제 안전을 보장하지 않아요.")).toBeInTheDocument();
    expect(screen.getByText("경로 데이터 안내")).toBeInTheDocument();
    expect(screen.getByText(/직선 연결 추정/)).toBeInTheDocument();
    expect(screen.getByText("경로 산출물 게시 시각")).toBeInTheDocument();
    expect(screen.getByText("범죄율 데이터: 1개 경유 동에서 확인할 수 없음")).toBeInTheDocument();
    expect(screen.getByText("직선 거리 추정으로 대체됨")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "검색 조건 수정" }));
    fireEvent.change(screen.getByLabelText("도착지 주소"), { target: { value: "29.44895, 132.25367" } });
    fireEvent.click(screen.getByRole("button", { name: "추천 경로 찾기" }));

    await waitFor(() => expect(screen.queryByLabelText("경로 검색 결과")).not.toBeInTheDocument());
  });
});
