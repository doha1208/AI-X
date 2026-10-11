import { describe, expect, it } from "vitest";
import { parsePx, visibleMapInsets } from "./mapInsets";

describe("visibleMapInsets", () => {
  it("adds no padding on desktop, where the panel sits beside the map", () => {
    expect(visibleMapInsets(false, 400)).toEqual({ top: 0, right: 0, bottom: 0, left: 0 });
  });

  it("keeps the route clear of the bottom sheet and the top card on mobile", () => {
    const insets = visibleMapInsets(true, 312);
    expect(insets.bottom).toBeGreaterThanOrEqual(312);
    expect(insets.top).toBeGreaterThan(0);
    expect(insets.left).toBe(0);
    expect(insets.right).toBe(0);
  });

  it("grows with the sheet, so an expanded sheet pushes the route higher", () => {
    expect(visibleMapInsets(true, 400).bottom).toBeGreaterThan(visibleMapInsets(true, 104).bottom);
  });

  it("still leaves room for the collapsed sheet when its height is unknown", () => {
    expect(visibleMapInsets(true, 0).bottom).toBeGreaterThan(0);
  });
});

describe("parsePx", () => {
  it("reads a CSS pixel value", () => {
    expect(parsePx("312px")).toBe(312);
    expect(parsePx(" 104.5px ")).toBe(104.5);
  });

  it("returns 0 for anything that is not a pixel value", () => {
    expect(parsePx("")).toBe(0);
    expect(parsePx("auto")).toBe(0);
    expect(parsePx("calc(1px + 2px)")).toBe(0);
  });
});
