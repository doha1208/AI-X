import { haversineMeters } from "./geo";
import type { LatLng } from "./kakao";

export type Fix = LatLng & { accuracy: number; time: number };

// GPS를 우선 쓰고(enableHighAccuracy), 캐시된 옛 위치는 받지 않는다.
export const GEO_OPTIONS: PositionOptions = { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 };

// 이보다 부정확한 값(기지국·IP 기반 위치)은 더 정확한 위치를 이미 갖고 있으면 버린다.
const MAX_ACCURACY_M = 100;
// 걷거나 뛰어서는 나올 수 없는 속도로 움직였다면 GPS 값이 튄 것으로 본다.
const MAX_SPEED_MPS = 8;
// 이만큼 새 위치를 계속 버렸다면 실제로 이동한 것으로 보고 받아들인다(버스를 탔거나 이전 값이 틀렸던 경우).
const STALE_MS = 20000;

export function toFix(pos: GeolocationPosition): Fix {
  return { lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy, time: pos.timestamp };
}

// 새 위치를 받아들일지 정한다: 정확도가 크게 나빠진 값과, 순간이동처럼 튄 값을 걸러낸다.
export function acceptFix(prev: Fix | null, next: Fix): boolean {
  if (!prev) return true;
  if (next.accuracy > MAX_ACCURACY_M && next.accuracy > prev.accuracy) return false;
  if (next.time - prev.time > STALE_MS) return true;
  const seconds = Math.max(1, (next.time - prev.time) / 1000);
  // 두 값의 오차 범위만큼은 움직임으로 치지 않는다 — 부정확했던 첫 위치가 정확한 GPS 값으로 바로 교정되도록.
  const moved = haversineMeters(prev, next) - prev.accuracy - next.accuracy;
  return moved / seconds <= MAX_SPEED_MPS;
}

// 정확도 원은 내 위치 마커(약 16~30px)보다 눈에 띄게 클 때만 의미가 있다 — 이보다 작으면 그리지 않는다.
const CIRCLE_MIN_M = 15;
// 지도를 다시 그리는 비용 때문에 반경을 10m 단위로 올린다(GPS가 ±수 m 흔들려도 같은 원).
const CIRCLE_STEP_M = 10;
// 걸으면서 안내에 쓰려면 50m 안쪽은 되어야 한다(골목 한 블록 폭). 100m를 넘으면 어느 길인지조차 헷갈린다.
const WARN_LOW_M = 50;
const WARN_POOR_M = 100;
// 경고를 켠 뒤 이만큼 확실히 좋아져야 끈다(경계 근처에서 경고가 깜빡이지 않게).
const WARN_CLEAR_MARGIN_M = 10;
const POOR_CLEAR_MARGIN_M = 20;

export type AccuracyLevel = "ok" | "low" | "poor";

export function accuracyCircleRadius(accuracy: number): number | null {
  return accuracy >= CIRCLE_MIN_M ? Math.ceil(accuracy / CIRCLE_STEP_M) * CIRCLE_STEP_M : null;
}

export function accuracyLevel(accuracy: number, previous: AccuracyLevel = "ok"): AccuracyLevel {
  if (accuracy >= WARN_POOR_M || (previous === "poor" && accuracy >= WARN_POOR_M - POOR_CLEAR_MARGIN_M)) return "poor";
  if (accuracy >= WARN_LOW_M || (previous !== "ok" && accuracy >= WARN_LOW_M - WARN_CLEAR_MARGIN_M)) return "low";
  return "ok";
}
