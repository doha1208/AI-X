import { describe, expect, it } from "vitest";
import { movedPastLongPressTolerance, supportsMapLongPress } from "./longPress";

describe("map long press helpers", () => {
  it("allows small finger jitter but cancels when the pointer starts dragging", () => {
    expect(movedPastLongPressTolerance({ x: 10, y: 10 }, { x: 16, y: 17 })).toBe(false);
    expect(movedPastLongPressTolerance({ x: 10, y: 10 }, { x: 22, y: 10 })).toBe(true);
  });

  it("only enables long press for a primary touch or pen pointer", () => {
    expect(supportsMapLongPress("touch", true)).toBe(true);
    expect(supportsMapLongPress("pen", true)).toBe(true);
    expect(supportsMapLongPress("mouse", true)).toBe(false);
    expect(supportsMapLongPress("touch", false)).toBe(false);
  });
});
