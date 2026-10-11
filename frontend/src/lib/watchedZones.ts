import type { SafetyZone } from "./api";
import { readJson, writeJson } from "./preferences";

// score: 마지막으로 확인한 안전지수 — 다음에 열었을 때 이 값과 달라졌으면 알림을 보낸다.
export type WatchedZone = { dong_code: string; dong_name: string; lat: number; lng: number; score: number };

const WATCHED_KEY = "ansim:watched-zones";
export const MAX_WATCHED_ZONES = 5;

function isWatchedZone(value: unknown): value is WatchedZone {
  if (!value || typeof value !== "object") return false;
  const { dong_code, dong_name, lat, lng, score } = value as Record<string, unknown>;
  return (
    typeof dong_code === "string" &&
    typeof dong_name === "string" &&
    typeof lat === "number" &&
    typeof lng === "number" &&
    typeof score === "number"
  );
}

export function loadWatchedZones(): WatchedZone[] {
  const stored = readJson(WATCHED_KEY);
  return Array.isArray(stored) ? stored.filter(isWatchedZone).slice(0, MAX_WATCHED_ZONES) : [];
}

export function saveWatchedZones(list: WatchedZone[]): void {
  writeJson(WATCHED_KEY, list.slice(0, MAX_WATCHED_ZONES));
}

// 이미 관심 동네면 해제하고, 아니면 추가한다(가득 찼으면 그대로 둔다). 바뀐 목록을 돌려준다.
export function toggleWatchedZone(zone: SafetyZone): WatchedZone[] {
  const current = loadWatchedZones();
  if (current.some((z) => z.dong_code === zone.dong_code)) {
    const next = current.filter((z) => z.dong_code !== zone.dong_code);
    saveWatchedZones(next);
    return next;
  }
  if (current.length >= MAX_WATCHED_ZONES) return current;
  const next = [
    ...current,
    { dong_code: zone.dong_code, dong_name: zone.dong_name, lat: zone.lat, lng: zone.lng, score: zone.safety_score },
  ];
  saveWatchedZones(next);
  return next;
}

// 화면에 보이는 값(반올림한 점수)이 달라졌을 때만 알린다 — 0.3점 흔들림까지 알리면 소음이다.
export function applyScoreChanges(
  watched: readonly WatchedZone[],
  latest: readonly SafetyZone[]
): { next: WatchedZone[]; messages: string[] } {
  const messages: string[] = [];
  const next = watched.map((w) => {
    const current = latest.find((z) => z.dong_code === w.dong_code);
    if (!current) return w;
    const from = Math.round(w.score);
    const to = Math.round(current.safety_score);
    if (from !== to) {
      messages.push(`${w.dong_name} 안전지수가 ${from}점에서 ${to}점으로 ${to > from ? "올랐" : "내려갔"}어요`);
    }
    return { ...w, score: current.safety_score };
  });
  return { next, messages };
}
