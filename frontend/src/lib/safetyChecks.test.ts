import { describe, expect, it } from "vitest";
import { arrivalDeadline } from "./useArrivalCheck";
import { shouldRefetch } from "./useSafeHaven";

describe("arrivalDeadline", () => {
  it("waits at least ten minutes for a short walk", () => {
    expect(arrivalDeadline(0, 100)).toBe(10 * 60_000);
  });

  it("allows one and a half times the walking time for a long walk", () => {
    const deadline = arrivalDeadline(0, 4000);
    expect(deadline).toBeGreaterThan(10 * 60_000);
    expect(deadline % (60_000 / 2)).toBe(0);
  });
});

describe("shouldRefetch", () => {
  const here = { lat: 37.2665, lng: 127.0005 };
  const far = { lat: 37.2675, lng: 127.0005 }; // 약 110m 북쪽

  it("fetches the first time", () => {
    expect(shouldRefetch(null, here, 0)).toBe(true);
  });

  it("waits until the walker has moved far enough and enough time has passed", () => {
    expect(shouldRefetch({ at: here, ms: 0 }, here, 60_000)).toBe(false);
    expect(shouldRefetch({ at: here, ms: 0 }, far, 5_000)).toBe(false);
    expect(shouldRefetch({ at: here, ms: 0 }, far, 20_000)).toBe(true);
  });
});
