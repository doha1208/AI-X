import { describe, expect, it } from "vitest";
import type { RouteResult } from "./api";
import {
  formatDistance,
  guideOptions,
  nearestPointOnPath,
  nextTurn,
  progressAlong,
  walkingMinutes,
  zoneSummary,
} from "./routeGuidance";

const zone = (code: string, score: number) => ({ dong_code: code, dong_name: code, lat: 37.5, lng: 127, safety_score: score });

// 위도 0.001도 ≈ 111m. 북쪽으로 두 칸 간 뒤 동쪽/서쪽으로 꺾는 경로.
const start = { lat: 37.5, lng: 127.0 };
const north1 = { lat: 37.501, lng: 127.0 };
const corner = { lat: 37.502, lng: 127.0 };

describe("routeGuidance", () => {
  it("announces a right turn at the corner with the distance to it", () => {
    const turn = nextTurn([start, north1, corner, { lat: 37.502, lng: 127.001 }], start, 0);
    expect(turn.direction).toBe("right");
    expect(turn.vertex).toBe(2);
    expect(turn.distanceM).toBeGreaterThan(215);
    expect(turn.distanceM).toBeLessThan(230);
  });

  it("announces a left turn when the path bends west", () => {
    expect(nextTurn([start, north1, corner, { lat: 37.502, lng: 126.999 }], start, 0).direction).toBe("left");
  });

  it("ignores gentle bends and points at the destination on a straight path", () => {
    const straight = [start, north1, { lat: 37.502, lng: 127.0001 }];
    const turn = nextTurn(straight, start, 0);
    expect(turn.direction).toBe("arrive");
    expect(turn.vertex).toBe(2);
  });

  it("measures remaining distance from the nearest vertex and how far off-route we are", () => {
    const here = { lat: 37.501, lng: 127.0003 }; // north1에서 동쪽으로 약 26m 벗어남
    const progress = progressAlong([start, north1, corner], here);
    expect(progress.index).toBe(1);
    expect(progress.offRouteM).toBeGreaterThan(20);
    expect(progress.offRouteM).toBeLessThan(30);
    expect(progress.remainingM).toBeGreaterThan(130);
    expect(progress.totalM).toBeGreaterThan(220);
  });

  it("offers the safe route and the shortest route as choices when both exist", () => {
    const safePoints = [start, north1, corner];
    const result: RouteResult = {
      safety_score: 70,
      zones_passed: [zone("A", 80)],
      route_points: safePoints,
      mode: "safety_weighted",
      period: "day",
      alternatives: [{ route_points: safePoints, safety_score: 70, distance_m: 222, zones_passed: [zone("A", 80)] }],
      shortest_route_points: [start, corner],
      shortest_zones_passed: [zone("A", 80), zone("B", 30)],
    };

    const [safe, shortest] = guideOptions(result);

    expect(safe).toMatchObject({ kind: "safe", distanceM: 222 });
    expect(shortest.kind).toBe("shortest");
    expect(shortest.zones.map((z) => z.dong_code)).toEqual(["A", "B"]);
  });

  it("offers only one route when there is no shortest-route comparison", () => {
    const result: RouteResult = {
      safety_score: 50,
      zones_passed: [],
      route_points: [start, corner],
      mode: "tmap",
      period: "day",
      alternatives: [],
      shortest_route_points: null,
    };
    expect(guideOptions(result).map((o) => o.kind)).toEqual(["safe"]);
  });

  it("summarises the dongs a route passes with the same rule for every option", () => {
    expect(zoneSummary([zone("A", 80), zone("B", 30), zone("C", 40)])).toEqual({ average: 50, cautionCount: 1 });
    expect(zoneSummary([])).toEqual({ average: null, cautionCount: 0 });
  });

  it("snaps to the closest point on a segment, not just the nearest vertex", () => {
    // start(0,0)에서 north1(111m 북쪽)로 가는 직선 구간 중간, 동쪽으로 약 10m 벗어난 위치.
    const here = { lat: 37.5005, lng: 127.0001 };
    const { point, distanceM } = nearestPointOnPath([start, north1], here);

    expect(distanceM).toBeLessThan(15); // 두 꼭짓점까지의 거리(약 60m)보다 훨씬 가까워야 한다
    expect(point.lng).toBeCloseTo(127.0, 3); // 선분(경도 127.0) 위로 투영된다
  });

  it("formats walking time and distance for display", () => {
    expect(walkingMinutes(10)).toBe(1);
    expect(walkingMinutes(670)).toBe(10);
    expect(formatDistance(347)).toBe("350m");
    expect(formatDistance(1234)).toBe("1.2km");
  });
});
