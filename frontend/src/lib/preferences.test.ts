import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  addRecent,
  isValidPhone,
  loadEmergencyContacts,
  loadRecent,
  loadSettings,
  routeTimeFor,
  saveEmergencyContacts,
  saveSettings,
} from "./preferences";

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

  it("remembers keepScreenOn, defaulting to off for settings saved before it existed", () => {
    saveSettings({ ...DEFAULT_SETTINGS, keepScreenOn: true });
    expect(loadSettings()).toMatchObject({ keepScreenOn: true });

    localStorage.setItem("ansim:settings", JSON.stringify({ showBells: true, timeMode: "auto" }));
    expect(loadSettings().keepScreenOn).toBe(false);
  });

  it("keeps recents newest-first, without duplicates, capped at five", () => {
    const place = (label: string) => ({ label, lat: 37.5, lng: 127.0 });
    for (const label of ["a", "b", "c", "d", "e", "f"]) addRecent("searches", place(label));
    addRecent("searches", place("c"));
    expect(loadRecent("searches").map((e) => e.label)).toEqual(["c", "f", "e", "d", "b"]);
  });

  it("remembers recent places by coordinates, so choosing one again needs no re-geocoding", () => {
    addRecent("destinations", { label: "서울역", lat: 37.5547, lng: 126.9707 });
    expect(loadRecent("destinations")).toEqual([{ label: "서울역", lat: 37.5547, lng: 126.9707, at: expect.any(Number) }]);
  });

  it("drops recents saved before coordinates were stored, rather than crash on missing lat/lng", () => {
    localStorage.setItem("ansim:recent-destinations", JSON.stringify([{ label: "옛 기록", at: Date.now() }]));
    expect(loadRecent("destinations")).toEqual([]);
  });

  it("remembers emergency contacts, capped at three, dropping ones with no phone", () => {
    saveEmergencyContacts([
      { name: "엄마", phone: "010-1111-2222" },
      { name: "아빠", phone: "010-3333-4444" },
      { name: "친구", phone: "010-5555-6666" },
      { name: "여분", phone: "010-7777-8888" },
    ]);
    expect(loadEmergencyContacts()).toEqual([
      { name: "엄마", phone: "010-1111-2222" },
      { name: "아빠", phone: "010-3333-4444" },
      { name: "친구", phone: "010-5555-6666" },
    ]);

    localStorage.setItem("ansim:emergency-contacts", JSON.stringify([{ name: "번호 없음", phone: "" }]));
    expect(loadEmergencyContacts()).toEqual([]);
  });

  it("accepts only phone-shaped strings, so nothing else can ride into an sms: link", () => {
    expect(isValidPhone("010-1234-5678")).toBe(true);
    expect(isValidPhone("+82 10 1234 5678")).toBe(true);
    expect(isValidPhone("(02) 123-4567")).toBe(true);
    expect(isValidPhone("12")).toBe(false);
    expect(isValidPhone("010&body=x")).toBe(false);
    expect(isValidPhone("abc")).toBe(false);

    localStorage.setItem("ansim:emergency-contacts", JSON.stringify([{ name: "x", phone: "010?body=hi" }]));
    expect(loadEmergencyContacts()).toEqual([]);
  });

  it("pins day/night by sending a fixed KST time, and nothing for auto", () => {
    expect(routeTimeFor("auto")).toBeUndefined();
    expect(routeTimeFor("day")).toBe("2000-01-01T12:00:00+09:00");
    expect(routeTimeFor("night")).toBe("2000-01-01T23:00:00+09:00");
  });
});
