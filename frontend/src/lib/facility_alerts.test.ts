import { describe, expect, it } from "vitest";
import type { LocalEnvironment, RouteFacilityInterval } from "./api";
import { deriveFacilityAlert, FACILITY_ALERT_POLICY } from "./facility_alerts";

const absent = "absent_in_verified_inventory";
const range = (start_m: number, end_m: number, state: RouteFacilityInterval["state"] = absent) => ({ start_m, end_m, state });
const local = (state: "present" | "unknown" = "unknown"): LocalEnvironment => ({
  artifact_version: "v1", period: "night",
  point: [37.5, 127], model_version: "facility-access-v1", policy_version: "test",
  assessed_at: "2026-11-05T23:00:00+09:00", source_versions: {},
  factors: { open_store: { state, comparison_known: state === "present",
    comparison_present: state === "present", observed_present: state === "present" } },
});

const base = {
  routeId: "selected", artifactVersion: "v1", temporalKey: "thursday",
  period: "night" as const, policy: FACILITY_ALERT_POLICY, progressM: 0, nowMs: 1000,
  routeEvidence: { lighting: [range(0, 300)], open_store: [range(0, 300, "unknown")], bell: [range(0, 300, "present")] },
  localEnvironment: local(), previousState: null,
};

describe("verified walking facility gaps", () => {
  it("uses known lighting absence even with nearby bells and unknown shop hours", () => {
    const result = deriveFacilityAlert(base);
    expect(result.alert?.kind).toBe("lighting");
    expect(result.announce).toBe(true);
  });

  it("requires verified absence for the combined claim and suppresses alerts for nearby open stores or daytime", () => {
    const both = { ...base, routeEvidence: { lighting: [range(0, 300)], open_store: [range(0, 300)] } };
    expect(deriveFacilityAlert(both).alert?.kind).toBe("lighting_and_store");
    expect(deriveFacilityAlert({ ...both, localEnvironment: local("present") }).alert).toBeNull();
    expect(deriveFacilityAlert({ ...base, routeEvidence: { lighting: [range(0, 300, "unknown")] } }).alert).toBeNull();
    expect(deriveFacilityAlert({ ...base, routeEvidence: { ...base.routeEvidence, open_store: [range(0, 300, "present")] } }).alert).toBeNull();
    expect(deriveFacilityAlert({ ...base, period: "day" }).alert).toBeNull();
  });

  it("keeps a lighting-only gap continuous across an unknown store interval without broadening the claim", () => {
    const routeEvidence = { lighting: [range(0, 150)], open_store: [range(0, 80), range(80, 150, "unknown")] };
    const result = deriveFacilityAlert({ ...base, routeEvidence });
    expect(result.alert).toMatchObject({ kind: "lighting", startM: 0, endM: 150 });
  });

  it("triggers at 100m, keeps the same gap until less than 60m remains", () => {
    const withLength = (length: number) => ({ ...base, routeEvidence: { lighting: [range(0, length)] } });
    expect(deriveFacilityAlert(withLength(99.9)).alert).toBeNull();
    const started = deriveFacilityAlert(withLength(100));
    expect(started.alert).not.toBeNull();
    const maintained = { ...withLength(100), previousState: started.nextState };
    expect(deriveFacilityAlert({ ...maintained, progressM: 40 }).alert?.id).toBe(started.alert?.id);
    expect(deriveFacilityAlert({ ...maintained, progressM: 40.1 }).alert).toBeNull();
  });

  it("only announces within 20m of a gap and repeats no sooner than 180 seconds", () => {
    const ahead = { ...base, routeEvidence: { lighting: [range(50, 350)] } };
    const distant = deriveFacilityAlert({ ...ahead, progressM: 29.9 });
    expect(distant.alert).not.toBeNull();
    expect(distant.announce).toBe(false);
    const near = deriveFacilityAlert({ ...ahead, progressM: 30, previousState: distant.nextState });
    expect(near.announce).toBe(true);
    expect(near.alert?.id).toBe(distant.alert?.id);
    const walking = { ...ahead, progressM: 80, previousState: near.nextState };
    expect(deriveFacilityAlert({ ...walking, nowMs: 180999 }).announce).toBe(false);
    expect(deriveFacilityAlert({ ...walking, nowMs: 181000 }).announce).toBe(true);
  });

  it("requires matching point evidence and resets gap identity on route, artifact or schedule changes", () => {
    const first = deriveFacilityAlert(base);
    const later = { ...base, previousState: first.nextState };
    expect(deriveFacilityAlert({ ...later, artifactVersion: "v2" }).alert).toBeNull();
    expect(deriveFacilityAlert({ ...later, localEnvironment: null }).alert).toBeNull();
    expect(deriveFacilityAlert({ ...later, enabled: false }).alert).toBeNull();
    const updated = deriveFacilityAlert({ ...later, temporalKey: "friday" });
    expect(updated.alert?.id).not.toBe(first.alert?.id);
    expect(updated.announce).toBe(false);
    expect(deriveFacilityAlert({ ...later, routeId: "rerouted" }).alert?.id).not.toBe(first.alert?.id);
  });
});
