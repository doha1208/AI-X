import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { routeEnvironment, type LiveFacilityReport } from "./api";
import { useSafeHaven } from "./useSafeHaven";

vi.mock("./api", () => ({ routeEnvironment: vi.fn() }));
const load = vi.mocked(routeEnvironment);
const start = { lat: 37.5, lng: 127 };
const routePoints = [start, { lat: 37.502, lng: 127 }];
const other = [start, { lat: 37.503, lng: 127 }];
const time = Date.parse("2026-11-05T23:00:00+09:00");

function report(version: string, lifetime = 60_000): LiveFacilityReport {
  const evaluated_at = new Date(Date.now()).toISOString();
  return {
    status: "degraded", period: "night", artifact_version: version, evaluated_at,
    valid_until: new Date(Date.now() + lifetime).toISOString(), temporal_key: version,
    assessment: null, route_evidence: {}, havens: [],
    local_environment: {
      point: [start.lat, start.lng], factors: {}, period: "night", artifact_version: version,
      model_version: "facility-access-v1", policy_version: "test", assessed_at: evaluated_at, source_versions: {},
    },
  };
}

function advance(ms: number) {
  return act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(time);
  load.mockReset();
});
afterEach(() => { vi.useRealTimers(); });

it("expires while stationary, hides stale evidence and observes the 15-second request floor", async () => {
  load.mockImplementationOnce(async () => report("v1", 10_000))
    .mockImplementation(async () => report("v2"));
  const { result } = renderHook(() => useSafeHaven(start, true, { routeId: "one", routePoints }));
  await advance(1);
  expect(result.current?.artifact_version).toBe("v1");
  await advance(9_999);
  expect(result.current).toBeNull();
  expect(load).toHaveBeenCalledTimes(1);
  await advance(5_000);
  expect(load).toHaveBeenCalledTimes(2);
  expect(result.current?.artifact_version).toBe("v2");
});

it("discards a late response for a replaced route even if the transport ignores abort", async () => {
  let finish!: (value: LiveFacilityReport) => void;
  load.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockImplementation(async () => report("new"));
  const { result, rerender } = renderHook(
    ({ points, routeId }) => useSafeHaven(start, true, { routeId, routePoints: points }),
    { initialProps: { points: routePoints, routeId: "one" } },
  );
  await advance(1);
  rerender({ points: other, routeId: "two" });
  expect(load.mock.calls[0][1]?.signal?.aborted).toBe(true);
  await act(async () => { finish(report("old")); });
  expect(result.current).toBeNull();
  await advance(15_000);
  expect(load).toHaveBeenCalledTimes(2);
  expect(load.mock.calls[1][0]).toBe(other);
  expect(result.current?.artifact_version).toBe("new");
});

it("suppresses older position evidence past 40m and clears it during rerouting", async () => {
  load.mockImplementation(async () => report("live"));
  const { result, rerender } = renderHook(
    ({ here, active }) => useSafeHaven(here, active, { routeId: "one", routePoints }),
    { initialProps: { here: start, active: true } },
  );
  await advance(1);
  expect(result.current).not.toBeNull();
  const moved = { lat: start.lat + 0.0005, lng: start.lng };
  rerender({ here: moved, active: true });
  expect(result.current).toBeNull();
  expect(load).toHaveBeenCalledTimes(1);
  await advance(15_000);
  expect(load.mock.calls[1][1]?.position).toEqual(moved);
  expect(result.current).not.toBeNull();
  rerender({ here: moved, active: false });
  expect(result.current).toBeNull();
});

it("rejects a response that mixes route and point artifact versions", async () => {
  load.mockImplementation(async () => {
    const value = report("route");
    return { ...value, local_environment: { ...value.local_environment!, artifact_version: "old" } };
  });
  const { result } = renderHook(() => useSafeHaven(start, true, { routeId: "one", routePoints }));
  await advance(1);
  expect(result.current).toBeNull();
});
