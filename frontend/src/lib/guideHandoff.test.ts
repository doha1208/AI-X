import { beforeEach, describe, expect, it } from "vitest";
import { loadHandoff, saveHandoff } from "./guideHandoff";
import type { GuideOption } from "./routeGuidance";

const end = { lat: 37.29, lng: 127.02 };
const option: GuideOption = {
  kind: "shortest",
  points: [{ lat: 37.28, lng: 127.01 }, end],
  zones: [],
  distanceM: 1400,
};

describe("guide handoff", () => {
  beforeEach(() => sessionStorage.clear());

  it("hands the chosen route to the guidance tab for the same destination", () => {
    saveHandoff(end, option, 1000);
    expect(loadHandoff({ lat: 37.29001, lng: 127.02001 }, 2000)).toEqual(option);
  });

  it("ignores a route saved for another destination", () => {
    saveHandoff(end, option, 1000);
    expect(loadHandoff({ lat: 37.3, lng: 127.02 }, 2000)).toBeNull();
  });

  it("ignores a stale route", () => {
    saveHandoff(end, option, 0);
    expect(loadHandoff(end, 11 * 60 * 1000)).toBeNull();
  });

  it("ignores broken storage content", () => {
    sessionStorage.setItem("guide-handoff", "{oops");
    expect(loadHandoff(end)).toBeNull();
  });
});
