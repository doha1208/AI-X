import { beforeEach, describe, expect, it } from "vitest";
import type { SafetyZone } from "./api";
import { applyScoreChanges, loadWatchedZones, MAX_WATCHED_ZONES, toggleWatchedZone } from "./watchedZones";

beforeEach(() => localStorage.clear());

const zone = (code: string, score: number): SafetyZone => ({
  dong_code: code,
  dong_name: `${code}동`,
  lat: 37.5,
  lng: 127.0,
  safety_score: score,
});

describe("watchedZones", () => {
  it("toggles a zone on and off", () => {
    expect(toggleWatchedZone(zone("A", 80)).map((z) => z.dong_code)).toEqual(["A"]);
    expect(loadWatchedZones()).toHaveLength(1);
    expect(toggleWatchedZone(zone("A", 80))).toEqual([]);
    expect(loadWatchedZones()).toEqual([]);
  });

  it("refuses to add past the limit, but still lets one be removed", () => {
    for (let i = 0; i < MAX_WATCHED_ZONES; i++) toggleWatchedZone(zone(`Z${i}`, 50));
    expect(toggleWatchedZone(zone("EXTRA", 50))).toHaveLength(MAX_WATCHED_ZONES);
    expect(loadWatchedZones().some((z) => z.dong_code === "EXTRA")).toBe(false);
    expect(toggleWatchedZone(zone("Z0", 50))).toHaveLength(MAX_WATCHED_ZONES - 1);
  });

  it("drops malformed stored entries", () => {
    localStorage.setItem("ansim:watched-zones", JSON.stringify([{ dong_code: "A" }, 3]));
    expect(loadWatchedZones()).toEqual([]);
  });
});

describe("applyScoreChanges", () => {
  it("reports a change in the score the user actually sees, and remembers the new score", () => {
    const watched = [toggleWatchedZone(zone("A", 71.2))[0]];
    const { next, messages } = applyScoreChanges(watched, [zone("A", 64.4)]);

    expect(messages).toEqual(["A동 안전지수가 71점에서 64점으로 내려갔어요"]);
    expect(next[0].score).toBe(64.4);
  });

  it("stays quiet when the displayed score is unchanged", () => {
    const watched = [toggleWatchedZone(zone("A", 71.2))[0]];
    expect(applyScoreChanges(watched, [zone("A", 70.6)]).messages).toEqual([]);
  });

  it("says raised when the score went up", () => {
    const watched = [toggleWatchedZone(zone("A", 40))[0]];
    expect(applyScoreChanges(watched, [zone("A", 55)]).messages).toEqual(["A동 안전지수가 40점에서 55점으로 올랐어요"]);
  });

  it("ignores a watched zone that is missing from the latest data", () => {
    const watched = [toggleWatchedZone(zone("A", 71))[0]];
    const { next, messages } = applyScoreChanges(watched, []);
    expect(messages).toEqual([]);
    expect(next).toEqual(watched);
  });
});
