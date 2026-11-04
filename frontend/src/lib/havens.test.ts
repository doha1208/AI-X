import { describe, expect, it } from "vitest";
import { bestHaven, havenDirectionsUrl } from "./havens";

describe("bestHaven", () => {
  it("prefers the nearest staffed place over a closer emergency bell", () => {
    const pick = bestHaven([
      { kind: "bell", lat: 0, lng: 0, distance_m: 30 },
      { kind: "police", lat: 0, lng: 0, distance_m: 400 },
      { kind: "convenience", lat: 0, lng: 0, distance_m: 120 },
    ]);
    expect(pick?.kind).toBe("convenience");
  });

  it("falls back to a bell when nothing staffed is near, and to null when nothing is", () => {
    expect(bestHaven([{ kind: "bell", lat: 0, lng: 0, distance_m: 30 }])?.kind).toBe("bell");
    expect(bestHaven([])).toBeNull();
  });
});

it("builds a Kakao Map link to the haven", () => {
  expect(havenDirectionsUrl({ kind: "police", lat: 37.1, lng: 127.2, distance_m: 10 })).toBe(
    `https://map.kakao.com/link/to/${encodeURIComponent("경찰서·지구대")},37.1,127.2`
  );
});
