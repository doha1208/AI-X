import type { LatLng } from "./kakao";
import type { GuideOption } from "./routeGuidance";

// 길찾기 탭에서 고른 경로를 길안내 탭으로 넘긴다. URL에 좌표 수백 개를 싣지 않으려고 sessionStorage를 쓴다.
const KEY = "guide-handoff";
// 오래전에 넘긴 경로가 나중에 같은 목적지로 안내할 때 섞이지 않게 한다.
const MAX_AGE_MS = 10 * 60 * 1000;
// 목적지가 이만큼(약 10m) 안에서 같으면 같은 요청으로 본다.
const SAME_PLACE_DEG = 0.0001;

type Handoff = { end: LatLng; option: GuideOption; savedAt: number };

export function saveHandoff(end: LatLng, option: GuideOption, now = Date.now()): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ end, option, savedAt: now } satisfies Handoff));
  } catch {
    // 저장이 막혀 있으면 길안내 탭이 현재 위치에서 경로를 새로 찾는다.
  }
}

export function loadHandoff(end: LatLng, now = Date.now()): GuideOption | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Handoff;
    const samePlace =
      Math.abs(saved.end.lat - end.lat) < SAME_PLACE_DEG && Math.abs(saved.end.lng - end.lng) < SAME_PLACE_DEG;
    const fresh = now - saved.savedAt <= MAX_AGE_MS;
    const valid = Array.isArray(saved.option?.points) && saved.option.points.length > 1;
    return samePlace && fresh && valid ? saved.option : null;
  } catch {
    return null;
  }
}
