import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { forwardRef, useImperativeHandle } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ResidencePage from "./page";

const residenceRecommend = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  residenceRecommend: (...args: unknown[]) => residenceRecommend(...args),
  nearbyZones: vi.fn(),
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

    fireEvent.click(screen.getByRole("button", { name: /강남구 역삼동/ }));
    expect(screen.getByRole("region", { name: "선택 안전구역 상세" })).toHaveTextContent("전체 1위");
  });
});
