import { useEffect, useRef, useState } from "react";
import { spotReport, type SpotReport } from "@/lib/api";
import { haversineMeters } from "@/lib/geo";
import type { LatLng } from "@/lib/kakao";

// 이만큼 걸었고, 마지막 조회 뒤 이만큼 시간이 지났을 때만 지금 자리의 점수·거점을 다시 묻는다 — 걸음마다 부르지 않게.
const REFETCH_MOVE_M = 40;
const REFETCH_MIN_MS = 15_000;

export function shouldRefetch(last: { at: LatLng; ms: number } | null, here: LatLng, nowMs: number): boolean {
  if (!last) return true;
  return haversineMeters(last.at, here) >= REFETCH_MOVE_M && nowMs - last.ms >= REFETCH_MIN_MS;
}

// 안내 중 지금 자리의 구간 점수와 가까운 안심 거점(파출소·24시 편의점·비상벨). 실패하면 직전 값을 그대로 둔다.
// 위치는 1초마다 바뀌므로 진행 중인 요청을 위치 변화로 취소하지 않는다 — 화면을 떠날 때만 결과를 버린다.
export function useSafeHaven(position: LatLng | null, active: boolean): SpotReport | null {
  const [report, setReport] = useState<SpotReport | null>(null);
  const lastRef = useRef<{ at: LatLng; ms: number } | null>(null);
  const activeRef = useRef(active);

  useEffect(() => {
    activeRef.current = active;
    if (!active) lastRef.current = null;
  }, [active]);

  useEffect(() => {
    if (!active || !position) return;
    const now = Date.now();
    if (!shouldRefetch(lastRef.current, position, now)) return;
    lastRef.current = { at: position, ms: now };
    spotReport(position.lat, position.lng)
      .then((next) => {
        if (activeRef.current) setReport(next);
      })
      .catch(() => {});
  }, [position, active]);

  // 안내가 끝나면 지난 결과를 보여주지 않는다(상태를 지우는 대신 여기서 가린다).
  return active ? report : null;
}
