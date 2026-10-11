import type { RouteResult, SafetyZone } from "./api";
import { haversineMeters } from "./geo";
import type { LatLng } from "./kakao";

// 도보 평균 4km/h.
const WALK_METERS_PER_MIN = 67;
// 경로 방향이 이만큼 이상 꺾이면 "회전"으로 안내한다. 보행 경로는 좌표가 촘촘해서
// 이보다 작은 꺾임은 길이 살짝 휘는 것일 뿐이다.
// ponytail: 한 꼭짓점의 꺾임만 본다 — 여러 짧은 구간에 걸쳐 도는 회전은 놓칠 수 있다.
const TURN_THRESHOLD_DEG = 45;

// 두 지점의 오차(위경도 몇백 m 안)에서는 위도 1도와 경도 1도 거리 비율이 이 값 정도로
// 고정된 것처럼 취급해도 근접점 계산 오차가 무시할 만큼 작다 — 서울·경기 위도(37.5도) 기준.
const LNG_SCALE = Math.cos((37.5 * Math.PI) / 180);

export type TurnDirection = "left" | "right" | "arrive";
export type Progress = { index: number; offRouteM: number; remainingM: number; totalM: number };
export type NextTurn = { direction: TurnDirection; distanceM: number; vertex: number };

export function pathLength(points: LatLng[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) total += haversineMeters(points[i - 1], points[i]);
  return total;
}

export function walkingMinutes(meters: number): number {
  return Math.max(1, Math.round(meters / WALK_METERS_PER_MIN));
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.max(10, Math.round(meters / 10) * 10)}m`;
  return `${(meters / 1000).toFixed(1)}km`;
}

function bearing(a: LatLng, b: LatLng): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const y = Math.sin(toRad(b.lng - a.lng)) * Math.cos(toRad(b.lat));
  const x =
    Math.cos(toRad(a.lat)) * Math.sin(toRad(b.lat)) -
    Math.sin(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.cos(toRad(b.lng - a.lng));
  return (Math.atan2(y, x) * 180) / Math.PI;
}

// 현재 위치에서 가장 가까운 경로 꼭짓점을 기준으로 이탈 거리와 남은 거리를 계산한다.
export function progressAlong(points: LatLng[], here: LatLng): Progress {
  let index = 0;
  let offRouteM = Infinity;
  points.forEach((point, i) => {
    const d = haversineMeters(here, point);
    if (d < offRouteM) {
      offRouteM = d;
      index = i;
    }
  });
  const remainingM = offRouteM + pathLength(points.slice(index));
  return { index, offRouteM, remainingM, totalM: pathLength(points) };
}

// 경로 위 실제로 가장 가까운 지점(꼭짓점이 아니라 선분 위 투영점)을 찾는다. 내 위치 마커를
// 경로에 붙여 보여줄 때(GPS 떨림 완화) 씀 — 꼭짓점만 보면 직선 구간 중간에서 튀어 보인다.
export function nearestPointOnPath(points: LatLng[], here: LatLng): { point: LatLng; distanceM: number } {
  if (points.length === 0) return { point: here, distanceM: 0 };
  const toXY = (p: LatLng) => ({ x: (p.lng - here.lng) * LNG_SCALE, y: p.lat - here.lat });
  const toLatLng = (x: number, y: number): LatLng => ({ lat: here.lat + y, lng: here.lng + x / LNG_SCALE });

  let best = { point: points[0], distanceM: haversineMeters(here, points[0]) };
  for (let i = 0; i < points.length - 1; i++) {
    const a = toXY(points[i]);
    const b = toXY(points[i + 1]);
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const lenSq = abx * abx + aby * aby;
    const t = lenSq === 0 ? 0 : Math.max(0, Math.min(1, (-a.x * abx + -a.y * aby) / lenSq));
    const candidate = toLatLng(a.x + abx * t, a.y + aby * t);
    const distanceM = haversineMeters(here, candidate);
    if (distanceM < best.distanceM) best = { point: candidate, distanceM };
  }
  return best;
}

export function nextTurn(points: LatLng[], here: LatLng, fromIndex: number): NextTurn {
  let distanceM = haversineMeters(here, points[fromIndex]);
  for (let j = fromIndex + 1; j < points.length - 1; j++) {
    distanceM += haversineMeters(points[j - 1], points[j]);
    const delta = ((bearing(points[j], points[j + 1]) - bearing(points[j - 1], points[j]) + 540) % 360) - 180;
    if (Math.abs(delta) >= TURN_THRESHOLD_DEG) {
      return { direction: delta > 0 ? "right" : "left", distanceM, vertex: j };
    }
  }
  const last = points.length - 1;
  if (last > fromIndex) distanceM += haversineMeters(points[last - 1], points[last]);
  return { direction: "arrive", distanceM, vertex: last };
}

export type GuideKind = "safe" | "shortest";
export type GuideOption = { kind: GuideKind; points: LatLng[]; zones: SafetyZone[]; distanceM: number };

// 길안내에서 고를 수 있는 경로: 안전 경로(가장 안전한 대안)와, 있으면 최단 경로.
export function guideOptions(result: RouteResult): GuideOption[] {
  const best = result.alternatives[0];
  const options: GuideOption[] = [
    {
      kind: "safe",
      points: best?.route_points ?? result.route_points,
      zones: best?.zones_passed ?? result.zones_passed,
      distanceM: best?.distance_m ?? pathLength(result.route_points),
    },
  ];
  const shortest = result.shortest_route_points;
  if (shortest && shortest.length > 1) {
    options.push({ kind: "shortest", points: shortest, zones: result.shortest_zones_passed ?? [], distanceM: pathLength(shortest) });
  }
  return options;
}

// 두 경로를 같은 기준으로 비교한다: 지나는 동의 평균 안전지수와 "주의"(40점 미만) 동의 수.
export function zoneSummary(zones: SafetyZone[]): { average: number | null; cautionCount: number } {
  if (zones.length === 0) return { average: null, cautionCount: 0 };
  const total = zones.reduce((sum, z) => sum + z.safety_score, 0);
  return { average: total / zones.length, cautionCount: zones.filter((z) => z.safety_score < 40).length };
}
