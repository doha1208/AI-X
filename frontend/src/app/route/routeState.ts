import type { Place } from "@/lib/place";

export type RouteDraft = { start: Place | null; end: Place | null };
export type RouteScreen = "idle" | "editing-start" | "editing-end" | "picking-start" | "picking-end" | "results";

export function canSearch(places: RouteDraft, loading: boolean): boolean {
  return Boolean(places.start && places.end) && !loading;
}

export function discardDraft(confirmed: RouteDraft): RouteDraft {
  return { ...confirmed };
}
