import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { AdaptiveBottomSheet } from "./AdaptiveBottomSheet";
import type { SheetSnap } from "@/lib/bottomSheet";

function Harness({ onChange = () => undefined }: { onChange?: (snap: SheetSnap) => void }) {
  const [snap, setSnap] = useState<SheetSnap>("collapsed");
  const workspaceRef = useRef<HTMLDivElement>(null);
  return (
    <div
      ref={(node) => {
        workspaceRef.current = node;
        if (node) Object.defineProperty(node, "clientHeight", { configurable: true, value: 800 });
      }}
      data-testid="workspace"
    >
      <AdaptiveBottomSheet
        label="경로 정보"
        snap={snap}
        onSnapChange={(next) => {
          setSnap(next);
          onChange(next);
        }}
        workspaceRef={workspaceRef}
        summary={<span>도보 12분 · 850m</span>}
      >
        <button type="button">상세 경로</button>
      </AdaptiveBottomSheet>
    </div>
  );
}

describe("AdaptiveBottomSheet", () => {
  it("advances its controlled snap when the handle is activated", () => {
    render(<Harness />);

    const handle = screen.getByRole("button", { name: "경로 정보 펼치기" });
    fireEvent.click(handle);

    expect(screen.getByRole("region", { name: "경로 정보" })).toHaveAttribute("data-snap", "half");
  });

  it("drags only from the handle and suppresses the click generated after a drag", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const handle = screen.getByRole("button", { name: "경로 정보 펼치기" });

    fireEvent.pointerDown(handle, { pointerId: 1, clientY: 700, button: 0 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientY: 360 });
    fireEvent.pointerUp(handle, { pointerId: 1, clientY: 360 });
    fireEvent.click(handle);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("region", { name: "경로 정보" })).toHaveAttribute("data-snap", "half");

    fireEvent.pointerDown(screen.getByRole("button", { name: "상세 경로" }), {
      pointerId: 2,
      clientY: 400,
      button: 0,
    });
    fireEvent.pointerMove(screen.getByRole("button", { name: "상세 경로" }), {
      pointerId: 2,
      clientY: 200,
    });
    fireEvent.pointerUp(screen.getByRole("button", { name: "상세 경로" }), {
      pointerId: 2,
      clientY: 200,
    });

    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("publishes its visible collapsed height to the workspace", () => {
    render(<Harness />);
    fireEvent(window, new Event("resize"));

    expect(screen.getByTestId("workspace").style.getPropertyValue("--adaptive-sheet-height")).toBe("104px");
  });

  it("uses the same half snap coordinate for CSS translation and control offset", () => {
    render(<Harness />);
    const handle = screen.getByRole("button", { name: "경로 정보 펼치기" });
    fireEvent.click(handle);
    fireEvent(window, new Event("resize"));

    expect(screen.getByTestId("workspace").style.getPropertyValue("--adaptive-sheet-height")).toBe("394px");

  });
});
