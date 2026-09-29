import { beforeEach, describe, expect, it } from "vitest";
import { DEFAULT_SETTINGS, addRecent, loadRecent, loadSettings, routeTimeFor, saveSettings } from "./preferences";

beforeEach(() => localStorage.clear());

describe("preferences", () => {
  it("falls back to defaults when stored settings are corrupt", () => {
    localStorage.setItem("ansim:settings", JSON.stringify({ showBells: "yes", timeMode: "noon" }));
    expect(loadSettings()).toEqual(DEFAULT_SETTINGS);
  });

  it("remembers the voice settings, and fills them in for settings saved before they existed", () => {
    saveSettings({ ...DEFAULT_SETTINGS, voiceOn: false, voiceVolume: 0.3 });
    expect(loadSettings()).toMatchObject({ voiceOn: false, voiceVolume: 0.3 });

    localStorage.setItem("ansim:settings", JSON.stringify({ showBells: false, timeMode: "night" }));
    expect(loadSettings()).toEqual({ ...DEFAULT_SETTINGS, showBells: false, timeMode: "night" });
  });

  it("keeps recents newest-first, without duplicates, capped at five", () => {
    for (const label of ["a", "b", "c", "d", "e", "f"]) addRecent("searches", label);
    addRecent("searches", "c");
    expect(loadRecent("searches").map((e) => e.label)).toEqual(["c", "f", "e", "d", "b"]);
  });

  it("pins day/night by sending a fixed KST time, and nothing for auto", () => {
    expect(routeTimeFor("auto")).toBeUndefined();
    expect(routeTimeFor("day")).toBe("2000-01-01T12:00:00+09:00");
    expect(routeTimeFor("night")).toBe("2000-01-01T23:00:00+09:00");
  });
});
