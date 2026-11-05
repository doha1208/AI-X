"use client";

import { useEffect, type RefObject } from "react";

export function useMapZoomGuard(workspaceRef: RefObject<HTMLElement | null>, enabled = true) {
  useEffect(() => {
    const workspace = workspaceRef.current;
    if (!enabled || !workspace) return;
    // Desktop trackpad pinches are Ctrl+wheel events. Kakao handles the map itself,
    // but its sibling panels and zoom buttons must not pass them to browser zoom.
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey) event.preventDefault();
    };
    workspace.addEventListener("wheel", onWheel, { passive: false });
    return () => workspace.removeEventListener("wheel", onWheel);
  }, [workspaceRef, enabled]);
}
