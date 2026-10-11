import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RoutePeek, type RoutePeekItem } from "./RoutePeek";

const items: RoutePeekItem[] = [
  { key: "0", label: "추천", minutes: 47, distance: "3.2km", score: "52점", active: true },
  { key: "1", label: "대안 1", minutes: 48, distance: "3.2km", score: "53점", active: false },
  { key: "shortest", label: "최단 경로", minutes: 44, distance: "3.0km", active: false },
];

describe("RoutePeek", () => {
  it("shows every route as a chip with its time, distance and score", () => {
    render(<RoutePeek items={items} onSelect={() => {}} onStart={() => {}} />);

    expect(screen.getByRole("button", { name: /추천 47분 3\.2km · 52점/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /대안 1 48분/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /최단 경로 44분 3\.0km/ })).toBeInTheDocument();
  });

  it("reports which route was tapped", () => {
    const onSelect = vi.fn();
    render(<RoutePeek items={items} onSelect={onSelect} onStart={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /대안 1/ }));

    expect(onSelect).toHaveBeenCalledWith("1");
  });

  it("starts guidance from the selected route", () => {
    const onStart = vi.fn();
    render(<RoutePeek items={items} onSelect={() => {}} onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: "안내 시작" }));

    expect(onStart).toHaveBeenCalledTimes(1);
  });
});
