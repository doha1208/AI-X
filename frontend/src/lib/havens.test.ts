import { describe, expect, it } from "vitest";
import { bestHaven, havenDirectionsUrl } from "./havens";

describe("bestHaven", () => {
  it("does not infer that any location is staffed when picking the closest known position", () => {
    const pick = bestHaven([
      { kind: "bell", lat: 0, lng: 0, distance_m: 30 },
      { kind: "police", lat: 0, lng: 0, distance_m: 400 },
      { kind: "convenience", lat: 0, lng: 0, distance_m: 120 },
    ]);
    expect(pick?.kind).toBe("bell");
  });

  it("uses a bell position when that is the only observation, and null when nothing is observed", () => {
    expect(bestHaven([{ kind: "bell", lat: 0, lng: 0, distance_m: 30 }])?.kind).toBe("bell");
    expect(bestHaven([])).toBeNull();
  });

  it("does not recommend a store outside its verified scheduled hours", () => {
    const pick = bestHaven([
      { kind: "convenience", lat: 0, lng: 0, distance_m: 10, opening_status: "scheduled_closed" },
      { kind: "bell", lat: 0, lng: 0, distance_m: 30, opening_status: "not_applicable" },
    ]);
    expect(pick?.kind).toBe("bell");
  });
});

it("builds a Kakao Map link to the haven", () => {
  expect(havenDirectionsUrl({ kind: "police", lat: 37.1, lng: 127.2, distance_m: 10 })).toBe(
    `https://map.kakao.com/link/to/${encodeURIComponent("경찰서·지구대")},37.1,127.2`
  );
});
