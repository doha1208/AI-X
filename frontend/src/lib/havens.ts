import type { SafeHaven, SafeHavenKind } from "@/lib/api";

export const HAVEN_LABEL: Record<SafeHavenKind, string> = {
  police: "경찰서·지구대",
  convenience: "24시 편의점",
  bell: "안전비상벨",
};

// 이 점수 미만인 자리에 들어서면 "주변이 어두워요" 경고와 함께 가까운 안심 거점을 보여준다(동 점수 "주의" 기준과 같다).
export const LOW_SPOT_SCORE = 40;

// 카카오맵 길찾기로 거점까지 바로 안내한다 — 진행 중인 귀갓길 안내는 그대로 둔다.
export function havenDirectionsUrl(haven: SafeHaven): string {
  return `https://map.kakao.com/link/to/${encodeURIComponent(HAVEN_LABEL[haven.kind])},${haven.lat},${haven.lng}`;
}

// 도움을 청하러 갈 곳은 사람이 있는 곳이 먼저다 — 비상벨은 다른 거점이 없을 때만 고른다.
export function bestHaven(havens: SafeHaven[]): SafeHaven | null {
  const staffed = havens.filter((h) => h.kind !== "bell");
  const pool = staffed.length > 0 ? staffed : havens;
  return pool.reduce<SafeHaven | null>((best, h) => (!best || h.distance_m < best.distance_m ? h : best), null);
}
