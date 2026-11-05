import type { SafeHaven, SafeHavenKind } from "@/lib/api";

type HavenLocation = Pick<SafeHaven, "kind" | "lat" | "lng" | "distance_m">;

export const HAVEN_LABEL: Record<SafeHavenKind, string> = {
  police: "경찰서·지구대",
  convenience: "편의점",
  bell: "안전비상벨",
};

// 카카오맵 길찾기로 거점까지 바로 안내한다 — 진행 중인 귀갓길 안내는 그대로 둔다.
export function havenDirectionsUrl(haven: HavenLocation): string {
  return `https://map.kakao.com/link/to/${encodeURIComponent(HAVEN_LABEL[haven.kind])},${haven.lat},${haven.lng}`;
}

export function bestHaven<T extends HavenLocation & Partial<Pick<SafeHaven, "opening_status">>>(havens: T[]): T | null {
  return havens.reduce<T | null>((best, h) => (
    h.opening_status !== "scheduled_closed" && (!best || h.distance_m < best.distance_m) ? h : best
  ), null);
}

export function havenAvailabilityText(haven: SafeHaven): string {
  const opening = {
    scheduled_open: "시간표상 영업 시간", scheduled_closed: "시간표상 영업시간 아님",
    unverified: "영업 미확인", not_applicable: null,
  }[haven.opening_status];
  return [opening, haven.staffing_status === "unverified" && "유인 미확인",
    haven.operation_status === "unverified" && "작동 미확인"].filter(Boolean).join(" · ");
}
