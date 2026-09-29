"use client";

import { useEffect } from "react";

// 길안내 중 화면이 꺼지면 위치 갱신·음성 안내가 함께 멈춘다 — active인 동안 화면 꺼짐을 막는다.
// 브라우저가 API를 지원하지 않거나(구형 iOS Safari 등) 탭이 백그라운드로 가서 브라우저가
// 알아서 잠금을 풀어도 조용히 넘어간다 — 화면 꺼짐 방지는 편의 기능이지 필수 기능이 아니다.
export function useWakeLock(active: boolean): void {
  useEffect(() => {
    if (!active || !("wakeLock" in navigator)) return;
    let lock: WakeLockSentinel | null = null;
    let cancelled = false;

    async function acquire() {
      try {
        const sentinel = await navigator.wakeLock.request("screen");
        if (cancelled) {
          await sentinel.release();
          return;
        }
        lock = sentinel;
        // 브라우저가 백그라운드 탭의 잠금을 풀면 sentinel만 남는다 — 비워야 visibilitychange가 재획득한다.
        sentinel.addEventListener("release", () => {
          if (lock === sentinel) lock = null;
        });
      } catch {
        // NotAllowedError(백그라운드 탭 등) — 다시 포그라운드로 오면 visibilitychange가 재시도한다.
      }
    }

    function onVisibilityChange() {
      if (document.visibilityState === "visible" && !lock) void acquire();
    }

    void acquire();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      lock?.release().catch(() => {});
    };
  }, [active]);
}
