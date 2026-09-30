"use client";

import {
  useCallback,
  useLayoutEffect,
  useRef,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { nextSheetSnap, settleSheetSnap, sheetSnapLayout, type SheetSnap } from "@/lib/bottomSheet";
import styles from "./AdaptiveBottomSheet.module.css";

const COLLAPSED_HEIGHT = 104;
const FULL_TOP_GAP = 12;

type Props = {
  label: string;
  snap: SheetSnap;
  onSnapChange: (snap: SheetSnap) => void;
  summary: ReactNode;
  children: ReactNode;
  className?: string;
  workspaceRef?: RefObject<HTMLElement | null>;
};

type DragState = {
  pointerId: number;
  startY: number;
  startOffset: number;
  startedAt: number;
  moved: boolean;
};

function snapOffsets(workspaceHeight: number): Record<SheetSnap, number> {
  return sheetSnapLayout(workspaceHeight, COLLAPSED_HEIGHT, FULL_TOP_GAP).offsets;
}

function handleLabel(label: string, snap: SheetSnap): string {
  if (snap === "collapsed") return `${label} 펼치기`;
  if (snap === "half") return `${label} 전체 화면으로 펼치기`;
  return `${label} 접기`;
}

export function AdaptiveBottomSheet({
  label,
  snap,
  onSnapChange,
  summary,
  children,
  className = "",
  workspaceRef,
}: Props) {
  const sheetRef = useRef<HTMLElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const suppressClickRef = useRef(false);

  const resolveWorkspace = useCallback(
    () => workspaceRef?.current ?? sheetRef.current?.parentElement ?? null,
    [workspaceRef]
  );

  const publishOffset = useCallback((offset?: number) => {
    const workspace = resolveWorkspace();
    if (!workspace) return;
    const layout = sheetSnapLayout(workspace.clientHeight, COLLAPSED_HEIGHT, FULL_TOP_GAP);
    const height = layout.height;
    const resolvedOffset = offset ?? layout.offsets[snap];
    workspace.style.setProperty("--adaptive-sheet-height", `${Math.max(0, height - resolvedOffset)}px`);
  }, [resolveWorkspace, snap]);

  useLayoutEffect(() => {
    const workspace = resolveWorkspace();
    if (!workspace) return;
    publishOffset();
    const onResize = () => publishOffset();
    window.addEventListener("resize", onResize);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(onResize);
    observer?.observe(workspace);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", onResize);
      workspace.style.removeProperty("--adaptive-sheet-height");
    };
  }, [publishOffset, resolveWorkspace]);

  function onPointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    const workspace = resolveWorkspace();
    if (!workspace) return;
    const offsets = snapOffsets(workspace.clientHeight);
    dragRef.current = {
      pointerId: event.pointerId,
      startY: event.clientY,
      startOffset: offsets[snap],
      startedAt: event.timeStamp,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    const workspace = resolveWorkspace();
    if (!drag || drag.pointerId !== event.pointerId || !workspace) return;
    const offsets = snapOffsets(workspace.clientHeight);
    const deltaY = event.clientY - drag.startY;
    const nextOffset = Math.min(offsets.collapsed, Math.max(offsets.full, drag.startOffset + deltaY));
    if (Math.abs(deltaY) >= 4) drag.moved = true;
    sheetRef.current?.style.setProperty("--sheet-drag-offset", `${nextOffset}px`);
    sheetRef.current?.setAttribute("data-dragging", "true");
    publishOffset(nextOffset);
  }

  function finishDrag(event: ReactPointerEvent<HTMLButtonElement>, cancelled = false) {
    const drag = dragRef.current;
    const workspace = resolveWorkspace();
    if (!drag || drag.pointerId !== event.pointerId || !workspace) return;
    dragRef.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    sheetRef.current?.style.removeProperty("--sheet-drag-offset");
    sheetRef.current?.removeAttribute("data-dragging");

    if (cancelled || !drag.moved) {
      publishOffset();
      return;
    }

    const deltaY = event.clientY - drag.startY;
    const elapsed = Math.max(1, event.timeStamp - drag.startedAt);
    const next = settleSheetSnap({
      current: snap,
      currentOffset: drag.startOffset,
      snapOffsets: snapOffsets(workspace.clientHeight),
      deltaY,
      velocityY: deltaY / elapsed,
    });
    suppressClickRef.current = true;
    onSnapChange(next);
  }

  function onHandleClick() {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    onSnapChange(nextSheetSnap(snap));
  }

  return (
    <section
      ref={sheetRef}
      className={`${styles.sheet} ${className}`}
      data-snap={snap}
      role="region"
      aria-label={label}
    >
      <button
        type="button"
        className={styles.handle}
        aria-label={handleLabel(label, snap)}
        onClick={onHandleClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(event) => finishDrag(event)}
        onPointerCancel={(event) => finishDrag(event, true)}
      >
        <span className={styles.grabber} aria-hidden />
      </button>
      <div className={styles.summary}>{summary}</div>
      <div className={styles.content}>{children}</div>
    </section>
  );
}
