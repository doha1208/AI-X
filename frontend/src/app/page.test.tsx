import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ResidencePage from "./page";

const residenceRecommend = vi.fn();
const nearbyZones = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  residenceRecommend: (...args: unknown[]) => residenceRecommend(...args),
  nearbyZones: (...args: unknown[]) => nearbyZones(...args),
  nearbyBells: vi.fn(),
}));

vi.mock("@/lib/useSessionUser", () => ({
  useSessionUser: () => ({ id: 1, email: "user@example.com" }),
  userInitial: () => "U",
}));

vi.mock("@/lib/useMyLocation", () => ({
  useMyLocation: () => ({ location: { lat: 37.5, lng: 127 }, denied: false, request: vi.fn() }),
}));

vi.mock("@/components/SafetyMap", () => ({
  SafetyMap: forwardRef(function MockSafetyMap(_props, ref) {
    useImperativeHandle(ref, () => ({ zoomIn: vi.fn(), zoomOut: vi.fn(), panTo: vi.fn() }));
    return <div data-testid="safety-map" />;
  }),
}));

describe("ResidencePage responsive presentation", () => {
  beforeEach(() => {
    residenceRecommend.mockResolvedValue([
      { dong_code: "1168064000", dong_name: "강남구 역삼동", lat: 37.5, lng: 127.03, safety_score: 82 },
    ]);
  });

  it("keeps one map and exposes ranking, legend, and search actions through the adaptive layout", async () => {
    render(<ResidencePage />);

    expect(await screen.findAllByText("강남구 역삼동")).not.toHaveLength(0);
    expect(screen.getAllByTestId("safety-map")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "안심 순위 펼치기" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "지도에서 선택" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "현재 위치" })).toBeInTheDocument();
    expect(screen.getAllByText("안전 (70~100)").length).toBeGreaterThan(0);
    await waitFor(() => expect(residenceRecommend).toHaveBeenCalledWith(10));

    // 순위 항목만 고른다 — 같은 줄의 "관심 동네 저장" 버튼 이름에도 동 이름이 들어 있다.
    fireEvent.click(screen.getByRole("button", { name: /강남구 역삼동(?! 관심)/ }));
    expect(screen.getByRole("region", { name: "선택 안전구역 상세" })).toHaveTextContent("전체 1위");
  });

  it("tells the user right away when a watched neighbourhood's score has changed", async () => {
    localStorage.setItem(
      "ansim:watched-zones",
      JSON.stringify([{ dong_code: "1168064000", dong_name: "강남구 역삼동", lat: 37.5, lng: 127.03, score: 82.4 }])
    );
    nearbyZones.mockResolvedValue([
      { dong_code: "1168064000", dong_name: "강남구 역삼동", lat: 37.5, lng: 127.03, safety_score: 70 },
    ]);

    render(<ResidencePage />);

    expect(await screen.findByRole("status")).toHaveTextContent("강남구 역삼동 안전지수가 82점에서 70점으로 내려갔어요");
    expect(JSON.parse(localStorage.getItem("ansim:watched-zones") ?? "[]")[0].score).toBe(70);

    fireEvent.click(screen.getByRole("button", { name: "알림 닫기" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
