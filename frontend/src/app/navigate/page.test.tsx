import { render, screen } from "@testing-library/react";
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

  it("returns direct visits to route planning without mounting a map", () => {
    render(<NavigatePage />);
    expect(screen.queryByTestId("safety-map")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "길찾기로 이동" })).toHaveAttribute("href", "/route");
  });
});
