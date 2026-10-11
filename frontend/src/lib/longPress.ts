export const LONG_PRESS_DELAY_MS = 550;
export const LONG_PRESS_MOVE_TOLERANCE_PX = 10;

export type ScreenPoint = { x: number; y: number };

export function movedPastLongPressTolerance(
  start: ScreenPoint,
  current: ScreenPoint,
  tolerance = LONG_PRESS_MOVE_TOLERANCE_PX
): boolean {
  return Math.hypot(current.x - start.x, current.y - start.y) > tolerance;
}

export function supportsMapLongPress(pointerType: string, isPrimary: boolean): boolean {
  return isPrimary && (pointerType === "touch" || pointerType === "pen");
}
