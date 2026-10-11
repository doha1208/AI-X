export type SheetSnap = "collapsed" | "half" | "full";

export function sheetSnapLayout(workspaceHeight: number, collapsedHeight = 104, topGap = 12) {
  const height = Math.max(collapsedHeight, workspaceHeight - topGap);
  const offsets: Record<SheetSnap, number> = {
    full: 0,
    half: Math.round(height / 2),
    collapsed: Math.max(0, height - collapsedHeight),
  };
  return { height, offsets };
}

const ORDER: SheetSnap[] = ["full", "half", "collapsed"];
const FLICK_VELOCITY = 0.45;
const STATIONARY_DISTANCE = 16;

type SettleSheetSnapInput = {
  current: SheetSnap;
  currentOffset: number;
  snapOffsets: Record<SheetSnap, number>;
  deltaY: number;
  velocityY: number;
};

export function settleSheetSnap({
  current,
  currentOffset,
  snapOffsets,
  deltaY,
  velocityY,
}: SettleSheetSnapInput): SheetSnap {
  const currentIndex = ORDER.indexOf(current);
  if (Math.abs(velocityY) >= FLICK_VELOCITY) {
    const direction = velocityY < 0 ? -1 : 1;
    return ORDER[Math.min(ORDER.length - 1, Math.max(0, currentIndex + direction))];
  }
  if (Math.abs(deltaY) < STATIONARY_DISTANCE) return current;

  const targetOffset = currentOffset + deltaY;
  return ORDER.reduce((nearest, candidate) =>
    Math.abs(snapOffsets[candidate] - targetOffset) < Math.abs(snapOffsets[nearest] - targetOffset)
      ? candidate
      : nearest
  , current);
}

export function nextSheetSnap(current: SheetSnap): SheetSnap {
  if (current === "collapsed") return "half";
  if (current === "half") return "full";
  return "collapsed";
}
