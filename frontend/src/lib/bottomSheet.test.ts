import { describe, expect, it } from "vitest";
import { settleSheetSnap, sheetSnapLayout, type SheetSnap } from "./bottomSheet";

const snapOffsets: Record<SheetSnap, number> = {
  full: 0,
  half: 300,
  collapsed: 600,
};

describe("settleSheetSnap", () => {
  it("shares one coordinate system between CSS translation and visible height", () => {
    const layout = sheetSnapLayout(800);
    expect(layout).toEqual({
      height: 788,
      offsets: { full: 0, half: 394, collapsed: 684 },
    });
    expect(layout.height - layout.offsets.half).toBe(394);
  });

  it("keeps the current snap after a stationary gesture", () => {
    expect(
      settleSheetSnap({ current: "half", currentOffset: 300, snapOffsets, deltaY: 5, velocityY: 0.05 })
    ).toBe("half");
  });

  it("chooses the nearest snap after a meaningful drag", () => {
    expect(
      settleSheetSnap({ current: "half", currentOffset: 300, snapOffsets, deltaY: -160, velocityY: -0.1 })
    ).toBe("full");
    expect(
      settleSheetSnap({ current: "half", currentOffset: 300, snapOffsets, deltaY: 170, velocityY: 0.1 })
    ).toBe("collapsed");
  });

  it("biases a fast flick to the adjacent snap in its direction", () => {
    expect(
      settleSheetSnap({ current: "half", currentOffset: 300, snapOffsets, deltaY: -12, velocityY: -0.7 })
    ).toBe("full");
    expect(
      settleSheetSnap({ current: "half", currentOffset: 300, snapOffsets, deltaY: 12, velocityY: 0.7 })
    ).toBe("collapsed");
  });

  it("does not move beyond the full or collapsed bounds", () => {
    expect(
      settleSheetSnap({ current: "full", currentOffset: 0, snapOffsets, deltaY: -80, velocityY: -0.8 })
    ).toBe("full");
    expect(
      settleSheetSnap({ current: "collapsed", currentOffset: 600, snapOffsets, deltaY: 80, velocityY: 0.8 })
    ).toBe("collapsed");
  });
});
