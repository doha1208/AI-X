import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";

vi.mock("next/navigation", () => ({ usePathname: () => "/route" }));

describe("AppHeader", () => {
  it("keeps route planning in the primary navigation but not live navigation", () => {
    render(<AppHeader userInitial="테" />);
    expect(screen.getByRole("link", { name: "길찾기" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "길안내" })).not.toBeInTheDocument();
  });

  it("opens secondary destinations from the menu and marks the active primary page", () => {
    render(<AppHeader userInitial="테" />);
    const navigation = screen.getByRole("navigation", { name: "주요 메뉴" });
    expect(within(navigation).getAllByRole("link")).toHaveLength(2);
    expect(within(navigation).getByRole("link", { name: "길찾기" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "집 리포트" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    const secondary = screen.getByRole("navigation", { name: "기타 메뉴" });
    expect(within(secondary).getByRole("link", { name: "집 리포트" })).toHaveAttribute("href", "/report");
    expect(within(secondary).getByRole("link", { name: "내 정보" })).toHaveAttribute("href", "/me");
    expect(within(secondary).getByRole("link", { name: "데이터 출처" })).toHaveAttribute("href", "/data");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("navigation", { name: "기타 메뉴" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "메뉴 열기" })).toHaveFocus();
  });

  it("dismisses secondary navigation when clicking outside or choosing a destination", () => {
    render(<AppHeader userInitial="테" />);
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("navigation", { name: "기타 메뉴" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "메뉴 열기" }));
    const report = screen.getByRole("link", { name: "집 리포트" });
    report.addEventListener("click", event => event.preventDefault());
    fireEvent.click(report);
    expect(screen.queryByRole("navigation", { name: "기타 메뉴" })).not.toBeInTheDocument();
  });
});
