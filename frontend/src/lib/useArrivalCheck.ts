import { useEffect, useState } from "react";
import { walkingMinutes } from "@/lib/routeGuidance";

// 예상 걸음 시간의 1.5배(최소 10분)가 지나도 도착하지 않으면 "괜찮으세요?"를 묻는다.
const SLACK_RATIO = 1.5;
const MIN_WAIT_MS = 10 * 60_000;
// "괜찮아요"를 누르면 이만큼 더 기다린다.
export const SNOOZE_MS = 10 * 60_000;
const CHECK_EVERY_MS = 15_000;

export function arrivalDeadline(startMs: number, routeM: number): number {
  return startMs + Math.max(MIN_WAIT_MS, walkingMinutes(routeM) * SLACK_RATIO * 60_000);
}

// 웹에서는 문자를 자동으로 보낼 수 없다 — 기한이 지나면 알리기만 하고, 보호자 문자는 사용자가 한 번 눌러 보낸다.
// 경로를 다시 찾아도 기한은 안내를 처음 시작한 때 기준 그대로 둔다(우회할 때마다 늦춰지지 않게).
export function useArrivalCheck(active: boolean, routeM: number) {
  const [clock, setClock] = useState<{ deadline: number | null; now: number }>({ deadline: null, now: 0 });

  useEffect(() => {
    if (!active) return;
    const start = Date.now();
    // 기한은 시작할 때 한 번만 잡는다 — 남은 거리가 바뀔 때마다 다시 잡지 않는다.
    const tick = () => setClock((c) => ({ deadline: c.deadline ?? arrivalDeadline(start, routeM), now: Date.now() }));
    const first = window.setTimeout(tick, 0);
    const id = window.setInterval(tick, CHECK_EVERY_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
      setClock({ deadline: null, now: 0 });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  function snooze() {
    const now = Date.now();
    setClock({ deadline: now + SNOOZE_MS, now });
  }

  const overdue = active && clock.deadline !== null && clock.now >= clock.deadline;
  return { overdue, snooze };
}
