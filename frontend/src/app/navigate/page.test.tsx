import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NavigatePage from "./page";

// 테스트마다 주소창의 쿼리를 바꿀 수 있게 한다(비우면 목적지를 고르는 화면).
let searchQuery = "end=37.500000,127.000000&endName=테스트%20목적지";

vi.mock("next/navigation", () => ({
  usePathname: () => "/navigate",
  useSearchParams: () => new URLSearchParams(searchQuery),
}));

vi.mock("@/lib/useSessionUser", () => ({
  useSessionUser: () => ({ name: "테스트 사용자", email: "test@example.com" }),
  userInitial: () => "테",
}));

vi.mock("@/lib/useMyLocation", () => ({
  useMyLocation: () => ({ location: null, denied: false }),
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

describe("NavigatePage responsive presentation", () => {
  beforeEach(() => {
    localStorage.clear();
    searchQuery = "end=37.500000,127.000000&endName=테스트%20목적지";
  });

  it("keeps one map and presents route choice in the shared adaptive sheet", () => {
    render(<NavigatePage />);

    expect(screen.getAllByTestId("safety-map")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "안내 경로 선택 펼치기" })).toBeInTheDocument();
    expect(screen.getByText("어떤 길로 안내할까요?")).toBeInTheDocument();
  });

  it("keeps recent destinations folded until the user asks for them, so they do not cover the map", () => {
    searchQuery = "";
    localStorage.setItem(
      "ansim:recent-destinations",
      JSON.stringify([
        { label: "수원역", lat: 37.2658, lng: 126.9999, at: Date.now() },
        { label: "아주대학교", lat: 37.2846, lng: 127.0446, at: Date.now() },
      ])
    );

    render(<NavigatePage />);

    const toggle = screen.getByRole("button", { name: /최근 목적지/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /수원역/ })).not.toBeInTheDocument();

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: /수원역/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /아주대학교/ })).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.queryByRole("button", { name: /수원역/ })).not.toBeInTheDocument();
  });
});
