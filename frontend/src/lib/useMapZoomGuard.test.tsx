import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { expect, it } from "vitest";
import { useMapZoomGuard } from "./useMapZoomGuard";

function Workspace({ enabled = true }: { enabled?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useMapZoomGuard(ref, enabled);
  return <><div ref={ref}><button>지도 확대</button><div>검색 결과</div></div><button>바깥 화면</button></>;
}

it("keeps a desktop pinch or Ctrl+wheel over map controls from zooming the surrounding page", () => {
  render(<Workspace />);
  const event = new WheelEvent("wheel", { ctrlKey: true, deltaY: -100, bubbles: true, cancelable: true });
  fireEvent(screen.getByRole("button", { name: "지도 확대" }), event);
  expect(event.defaultPrevented).toBe(true);
});

it("preserves ordinary panel scrolling, zoom outside the map and listener cleanup", () => {
  const { unmount } = render(<Workspace />);
  const mapControl = screen.getByRole("button", { name: "지도 확대" });
  const ordinary = new WheelEvent("wheel", { deltaY: 100, bubbles: true, cancelable: true });
  fireEvent(mapControl, ordinary);
  expect(ordinary.defaultPrevented).toBe(false);
  const outside = new WheelEvent("wheel", { ctrlKey: true, deltaY: -100, bubbles: true, cancelable: true });
  fireEvent(screen.getByRole("button", { name: "바깥 화면" }), outside);
  expect(outside.defaultPrevented).toBe(false);
  unmount();
  const after = new WheelEvent("wheel", { ctrlKey: true, deltaY: -100, bubbles: true, cancelable: true });
  fireEvent(mapControl, after);
  expect(after.defaultPrevented).toBe(false);
});

it("attaches after the authenticated workspace becomes available", () => {
  const { rerender } = render(<Workspace enabled={false} />);
  rerender(<Workspace enabled />);
  const event = new WheelEvent("wheel", { ctrlKey: true, deltaY: -100, bubbles: true, cancelable: true });
  fireEvent(screen.getByRole("button", { name: "지도 확대" }), event);
  expect(event.defaultPrevented).toBe(true);
});
