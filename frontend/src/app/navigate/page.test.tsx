import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import NavigatePage from "./page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/navigate",
  useSearchParams: () => new URLSearchParams("end=37.500000,127.000000&endName=테스트%20목적지"),
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
  it("keeps one map and presents route choice in the shared adaptive sheet", () => {
    render(<NavigatePage />);

    expect(screen.getAllByTestId("safety-map")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "안내 경로 선택 펼치기" })).toBeInTheDocument();
    expect(screen.getByText("어떤 길로 안내할까요?")).toBeInTheDocument();
  });
});
