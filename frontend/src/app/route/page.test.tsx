import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RoutePage from "./page";
import { loadHandoff } from "@/lib/guideHandoff";
import { assessmentFixture, environmentRouteFixture } from "@/test/routeFixtures";

const routeSafety = vi.fn();
const searchAddressSuggestions = vi.fn();

vi.mock("@/lib/place", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/place")>(),
  searchAddressSuggestions: (...args: unknown[]) => searchAddressSuggestions(...args),
}));

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
    SafetyMap: React.forwardRef<HTMLDivElement, { comparePath?: unknown[] }>(function MockSafetyMap(props, ref) {
      return <div ref={ref} data-testid="safety-map" data-compare-points={props.comparePath?.length ?? 0} />;
    }),
  };
});

describe("RoutePage responsive presentation", () => {
  it("explains unknown portions as bounds for partial assessments", async () => {
    routeSafety.mockReset();
    searchAddressSuggestions.mockResolvedValue([]);
    const points = [{lat:37.2636,lng:127.0286},{lat:37.2666,lng:127.0316}];
    const assessment = {model_version:"facility-access-v1",policy_version:"environment-v1-draft",status:"degraded",period:"day",
      distance_m:700,score:null,active_factors:["cctv","bell","open_store"],used_factors:[],excluded_factors:{},
      factor_coverage:{},data_factor_availability_ratio:0,longest_support_gap_m:null,total_support_gap_m:null,
      gap_intervals:[],source_versions:{},comparison_group_id:"test",evaluation_basis:"partial_coverage",score_bounds:{lower:20,upper:80}};
    routeSafety.mockResolvedValueOnce({safety_score:null,zones_passed:[],route_points:points,mode:"tmap",period:"day",
      environment_model_applied:true,environment_assessment:assessment,
      data_disclosure:{data_basis:["tmap_pedestrian_route"],updated_at:null,missing_data:[],fallback:{applied:false,mode:"tmap",reason:"none"}},
      alternatives:[{route_points:points,safety_score:null,distance_m:700,zones_passed:[],environment_assessment:assessment}]});
    render(<RoutePage/>);
    fireEvent.change(screen.getByLabelText("출발지 주소"),{target:{value:"37.2636, 127.0286"}});
    fireEvent.change(screen.getByLabelText("도착지 주소"),{target:{value:"37.2666, 127.0316"}});
    fireEvent.click(screen.getByRole("button",{name:"추천 경로 찾기"}));
    await screen.findByLabelText("경로 검색 결과");
    fireEvent.click(screen.getByText("경로 데이터 안내"));
    expect(screen.getByText(/미확인 부분은 제외하지 않고/)).toBeVisible();
    expect(screen.queryByText(/확인할 수 없는 지표는 점수 계산에서 빼고/)).not.toBeInTheDocument();
  });
  it("removes the comparison card and chip while preserving the map comparison", async () => {
    routeSafety.mockReset();
    searchAddressSuggestions.mockResolvedValue([]);
    const points = [{ lat: 37.2636, lng: 127.0286 }, { lat: 37.2666, lng: 127.0316 }];
    routeSafety.mockResolvedValueOnce({
      safety_score: 70, zones_passed: [], route_points: points, mode: "safety_weighted", period: "day",
      environment_model_applied: false,
      data_disclosure: { data_basis: ["osm_walking_network"], updated_at: null, missing_data: [], fallback: { applied: false, mode: "safety_weighted", reason: null } },
      alternatives: [{ route_points: points, safety_score: 70, distance_m: 700, zones_passed: [] }],
      shortest_route_points: points, shortest_zones_passed: [],
    });
    render(<RoutePage />);
    fireEvent.change(screen.getByLabelText("출발지 주소"), { target: { value: "37.2636, 127.0286" } });
    fireEvent.change(screen.getByLabelText("도착지 주소"), { target: { value: "37.2666, 127.0316" } });
    fireEvent.click(screen.getByRole("button", { name: "추천 경로 찾기" }));
    const results = await screen.findByLabelText("경로 검색 결과");
    expect(within(results).getAllByRole("article")).toHaveLength(1);
    expect(within(screen.getByRole("group", { name: "경로 선택" })).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByTestId("safety-map")).toHaveAttribute("data-compare-points", "2");
    expect(within(results).getByText("점수 미산정")).toBeInTheDocument();
    expect(within(results).queryByText("추천 1순위")).not.toBeInTheDocument();
  });
  it("shows a failed route search error in the mobile search screen", async () => {
    routeSafety.mockReset();
    routeSafety.mockRejectedValue(new Error("직선거리 10km를 초과하는 보행 경로는 지원하지 않습니다"));
    searchAddressSuggestions.mockResolvedValue([]);
    render(<RoutePage />);

    fireEvent.change(screen.getByRole("combobox", { name: "출발지 주소" }), { target: { value: "37.302813, 126.866778" } });
    fireEvent.change(screen.getByRole("combobox", { name: "도착지 주소" }), { target: { value: "37.566500, 126.978000" } });
    fireEvent.click(screen.getByRole("button", { name: "추천 경로 찾기" }));

    expect(await within(screen.getByRole("region", { name: "길찾기" })).findByRole("alert"))
      .toHaveTextContent("직선거리 10km를 초과하는 보행 경로는 지원하지 않습니다");
  });

  it("uses the chosen destination coordinates when finding a route", async () => {
    searchAddressSuggestions.mockImplementation((query: string) => Promise.resolve(query.includes("팔달구")
      ? [{ label: "경기도 수원시 팔달구 인계동", lat: 37.2, lng: 127 }]
      : [{ label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 }]));
    routeSafety.mockRejectedValue(new Error("경로를 찾지 못했어요"));
    render(<RoutePage />);

    fireEvent.change(screen.getByRole("combobox", { name: "출발지 주소" }), { target: { value: "수원시 팔달구 인계" } });
    fireEvent.click(await screen.findByRole("option", { name: "경기도 수원시 팔달구 인계동" }));
    fireEvent.change(screen.getByRole("combobox", { name: "도착지 주소" }), { target: { value: "수원시 영통구 망포" } });
    fireEvent.click(await screen.findByRole("option", { name: "경기도 수원시 영통구 망포동" }));
    expect(screen.getByRole("combobox", { name: "출발지 주소" })).toHaveValue("경기도 수원시 팔달구 인계동");
    expect(screen.getByRole("combobox", { name: "도착지 주소" })).toHaveValue("경기도 수원시 영통구 망포동");
    fireEvent.click(screen.getByRole("button", { name: "추천 경로 찾기" }));

    await waitFor(() => expect(routeSafety).toHaveBeenCalledWith(37.2, 127, 37.24, 127.06, expect.any(Object)));
  });

  it("keeps one map and exposes route results through the adaptive sheet", () => {
    render(<RoutePage />);

    expect(screen.getAllByTestId("safety-map")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "경로 결과 펼치기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "출발지와 도착지 바꾸기" })).toBeInTheDocument();
  });

  it.each([null, 0, 55])("allows guidance without presenting retired safety_score %s as a current facility score", async (score) => {
    sessionStorage.clear();
    routeSafety.mockReset();
    routeSafety.mockResolvedValue({
      safety_score: score,
      zones_passed: [],
      route_points: [{ lat: 37.302, lng: 126.866 }, { lat: 37.31, lng: 126.87 }],
      mode: "tmap", period: "day",
      data_disclosure: { data_basis: ["tmap_pedestrian_route"], updated_at: null, missing_data: [],
        fallback: { applied: true, mode: "tmap", reason: "safety_weighted_unavailable" } },
      alternatives: [{ route_points: [{ lat: 37.302, lng: 126.866 }, { lat: 37.31, lng: 126.87 }],
        safety_score: score, distance_m: 1200, zones_passed: [] }],
      shortest_route_points: null, shortest_zones_passed: null,
    });
    render(<RoutePage />);
    fireEvent.change(screen.getByRole("combobox", { name: "출발지 주소" }), { target: { value: "37.302, 126.866" } });
    fireEvent.change(screen.getByRole("combobox", { name: "도착지 주소" }), { target: { value: "37.31, 126.87" } });
    fireEvent.click(screen.getByRole("button", { name: "추천 경로 찾기" }));
    expect(await screen.findByRole("region", { name: "경로 검색 결과" })).toBeInTheDocument();
    const results = screen.getByRole("region", { name: "경로 검색 결과" });
    expect(within(results).getByText("점수 미산정")).toBeInTheDocument();
    expect(within(results).queryByText("추천 1순위")).not.toBeInTheDocument();
    expect(within(results).queryByText(/참고 안전지수|시설 \d+점/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /실시간 안내 시작|이 경로로 안내 시작/ }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "실시간 안내 시작" }));
    expect(loadHandoff({ lat: 37.31, lng: 126.87 })?.points).toEqual([
      { lat: 37.302, lng: 126.866 }, { lat: 37.31, lng: 126.87 },
    ]);
  });

  it.each([0, 72.4])("shows server facility score %s and preserves the selected assessment for guidance", async (score) => {
    const response = environmentRouteFixture();
    const selectedAssessment = assessmentFixture({ score });
    const second = { ...response.alternatives[0], distance_m: 1250, environment_assessment: selectedAssessment };
    response.alternatives.push(second);
    routeSafety.mockReset();
    routeSafety.mockResolvedValue(response);
    render(<RoutePage />);
    fireEvent.change(screen.getByRole("combobox", { name: "출발지 주소" }), { target: { value: "37.302, 126.866" } });
    fireEvent.change(screen.getByRole("combobox", { name: "도착지 주소" }), { target: { value: "37.31, 126.87" } });
    fireEvent.click(screen.getByRole("button", { name: "추천 경로 찾기" }));
    const results = await screen.findByRole("region", { name: "경로 검색 결과" });
    expect(within(results).getByText("시설 97점")).toBeInTheDocument();
    const displayed = `시설 ${score.toFixed(0)}점`;
    expect(within(results).getByText(displayed)).toBeInTheDocument();
    expect(screen.queryByText("안전지수 미제공")).not.toBeInTheDocument();
    fireEvent.click(within(results).getByRole("button", { name: new RegExp(displayed) }));
    fireEvent.click(within(results).getByRole("button", { name: "실시간 안내 시작" }));
    const handoff = loadHandoff({ lat: 37.31, lng: 126.87 });
    expect(handoff?.environmentAssessment).toEqual(selectedAssessment);
    expect(handoff?.distanceM).toBe(second.distance_m);
    expect(handoff?.points).toEqual(second.route_points);
  });

  it("clears the previous route when a replacement search fails", async () => {
    routeSafety
      .mockResolvedValueOnce({
        safety_score: 55,
        zones_passed: [],
        route_points: [{ lat: 37.532, lng: 126.99 }, { lat: 37.548, lng: 127.01 }],
        mode: "tmap",
        period: "day",
        data_disclosure: {
          data_basis: ["tmap_pedestrian_route", "zone_safety_indicators"],
          updated_at: null,
          missing_data: [{ factor: "crime_rate", affected_zone_count: 1 }],
          fallback: { applied: true, mode: "tmap", reason: "safety_weighted_unavailable" },
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
    expect(screen.getByText(/Tmap 보행 경로/)).toBeInTheDocument();
    expect(screen.getByText("경로 산출물 게시 시각")).toBeInTheDocument();
    expect(screen.getByText("범죄율 데이터: 1개 경유 동에서 확인할 수 없음")).toBeInTheDocument();
    expect(screen.getByText("일반 도보 경로로 대체됨")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "검색 조건 수정" }));
    fireEvent.change(screen.getByLabelText("도착지 주소"), { target: { value: "29.44895, 132.25367" } });
    fireEvent.click(screen.getByRole("button", { name: "추천 경로 찾기" }));

    await waitFor(() => expect(screen.queryByLabelText("경로 검색 결과")).not.toBeInTheDocument());
  });
});
