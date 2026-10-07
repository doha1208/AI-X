import { describe, expect, it } from "vitest";
import { acceptFix, accuracyCircleRadius, accuracyLevel, type Fix } from "./locationFilter";

// 위도 0.001도 ≈ 111m
const fix = (lat: number, accuracy: number, time: number): Fix => ({ lat, lng: 127, accuracy, time });

describe("acceptFix", () => {
  it("accepts the first fix whatever its accuracy", () => {
    expect(acceptFix(null, fix(37.5, 1500, 0))).toBe(true);
  });

  it("rejects fixes outside Korea such as the 0,0 a sensorless browser reports", () => {
    expect(acceptFix(null, { lat: 0, lng: 0, accuracy: 0, time: 0 })).toBe(false);
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

describe("accuracyCircleRadius", () => {
  it("draws nothing when the error is smaller than the marker itself", () => {
    expect(accuracyCircleRadius(5)).toBeNull();
    expect(accuracyCircleRadius(14.9)).toBeNull();
  });

  it("rounds up to 10m steps so GPS jitter does not redraw the map", () => {
    expect(accuracyCircleRadius(15)).toBe(20);
    expect(accuracyCircleRadius(20)).toBe(20);
    expect(accuracyCircleRadius(21)).toBe(30);
    expect(accuracyCircleRadius(87)).toBe(90);
  });
});

describe("accuracyLevel", () => {
  it("is ok below 50m, low from 50m, poor from 100m", () => {
    expect(accuracyLevel(49)).toBe("ok");
    expect(accuracyLevel(50)).toBe("low");
    expect(accuracyLevel(99)).toBe("low");
    expect(accuracyLevel(100)).toBe("poor");
  });

  it("does not flicker: a raised warning clears only after a clear improvement", () => {
    expect(accuracyLevel(45, "low")).toBe("low");
    expect(accuracyLevel(39, "low")).toBe("ok");
    expect(accuracyLevel(85, "poor")).toBe("poor");
    expect(accuracyLevel(75, "poor")).toBe("low");
  });
});
