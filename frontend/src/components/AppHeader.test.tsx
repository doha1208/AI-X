import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";

vi.mock("next/navigation", () => ({ usePathname: () => "/route" }));

describe("AppHeader", () => {
  it("keeps route planning in the primary navigation but not live navigation", () => {
    render(<AppHeader userInitial="테" />);
    expect(screen.getByRole("link", { name: "길찾기" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "길안내" })).not.toBeInTheDocument();
  });
});
