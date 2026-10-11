import { describe, expect, it } from "vitest";
import { canSearch, discardDraft, type RouteDraft } from "./routeState";

const home = { label: "집", lat: 37.5, lng: 127 };
const station = { label: "역", lat: 37.6, lng: 127.1 };

describe("route editor state", () => {
  it("allows search only after both confirmed places are set", () => {
    expect(canSearch({ start: home, end: null }, false)).toBe(false);
    expect(canSearch({ start: home, end: station }, false)).toBe(true);
    expect(canSearch({ start: home, end: station }, true)).toBe(false);
  });

  it("discards a cancelled draft without changing confirmed places", () => {
    const confirmed: RouteDraft = { start: home, end: station };
    expect(discardDraft(confirmed)).toEqual(confirmed);
  });
});
