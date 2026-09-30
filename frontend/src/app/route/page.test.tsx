import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import RoutePage from "./page";

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
});
