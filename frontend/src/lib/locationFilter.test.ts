import { describe, expect, it } from "vitest";
import { acceptFix, type Fix } from "./locationFilter";

// 위도 0.001도 ≈ 111m
const fix = (lat: number, accuracy: number, time: number): Fix => ({ lat, lng: 127, accuracy, time });

describe("acceptFix", () => {
  it("accepts the first fix whatever its accuracy", () => {
    expect(acceptFix(null, fix(37.5, 1500, 0))).toBe(true);
  });

  it("accepts normal walking movement", () => {
    expect(acceptFix(fix(37.5, 10, 0), fix(37.5001, 10, 5000))).toBe(true); // 11m / 5s
  });

  it("rejects a 500m jump within two seconds", () => {
    expect(acceptFix(fix(37.5, 10, 0), fix(37.5045, 15, 2000))).toBe(false);
  });

  it("rejects a coarse network fix once a GPS fix is known", () => {
    expect(acceptFix(fix(37.5, 10, 0), fix(37.5, 800, 3000))).toBe(false);
    expect(acceptFix(fix(37.5, 10, 0), fix(37.5, 800, 60000))).toBe(false);
  });

  it("lets an accurate GPS fix correct a coarse first fix far away", () => {
    expect(acceptFix(fix(37.5, 1500, 0), fix(37.51, 12, 2000))).toBe(true);
  });

  it("accepts a far fix after the last accepted one has gone stale", () => {
    expect(acceptFix(fix(37.5, 10, 0), fix(37.52, 10, 30000))).toBe(true);
  });
});
