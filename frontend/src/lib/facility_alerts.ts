import type { LocalEnvironment, RouteFacilityInterval, RoutePeriod } from "./api";

export const FACILITY_ALERT_POLICY = {
  version: "walking-gap-v1",
  lookaheadM: 200, triggerM: 100, clearM: 60, startProximityM: 20, cooldownMs: 180_000,
};

type Kind = "lighting" | "lighting_and_store";
type Gap = { kind: Kind; startM: number; endM: number };
export type FacilityAlert = Gap & { id: string; contextId: string };
export type FacilityAlertState = { contextId: string; cooldownContext: string; activeId: string | null; announced: Record<string, number> };

type Inputs = {
  routeId: string;
  artifactVersion: string;
  temporalKey: string;
  period: RoutePeriod;
  progressM: number;
  routeEvidence: Record<string, RouteFacilityInterval[]>;
  localEnvironment: LocalEnvironment | null;
  policy?: typeof FACILITY_ALERT_POLICY;
  previousState: FacilityAlertState | null;
  nowMs: number;
  enabled?: boolean;
};

const ABSENT = "absent_in_verified_inventory";

function gapIntervals(evidence: Inputs["routeEvidence"]): Gap[] {
  const lighting: Gap[] = [];
  const combined: Gap[] = [];
  const stores = evidence.open_store ?? [];
  let i = 0;
  function append(gaps: Gap[], kind: Kind, startM: number, endM: number) {
    if (endM <= startM) return;
    const last = gaps.at(-1);
    if (last?.kind === kind && last.endM === startM) last.endM = endM;
    else gaps.push({ kind, startM, endM });
  }
  for (const light of evidence.lighting ?? []) {
    if (light.state !== ABSENT) continue;
    let cursor = light.start_m;
    while (cursor < light.end_m) {
      while (i < stores.length && stores[i].end_m <= cursor) i++;
      const store = stores[i];
      if (!store || store.start_m >= light.end_m) {
        append(lighting, "lighting", cursor, light.end_m);
        break;
      }
      if (cursor < store.start_m) append(lighting, "lighting", cursor, store.start_m);
      const end = Math.min(store.end_m, light.end_m);
      const start = Math.max(cursor, store.start_m);
      if (store.state !== "present") append(lighting, "lighting", start, end);
      if (store.state === ABSENT) append(combined, "lighting_and_store", start, end);
      cursor = end;
    }
  }
  return [...combined, ...lighting];
}

export function facilityAlertContext(routeId: string, artifactVersion: string, temporalKey: string): string {
  return JSON.stringify([routeId, artifactVersion, temporalKey]);
}

export function deriveFacilityAlert({
  routeId, artifactVersion, temporalKey, period, progressM, routeEvidence, localEnvironment,
  policy = FACILITY_ALERT_POLICY, previousState, nowMs, enabled = true,
}: Inputs): { nextState: FacilityAlertState; alert: FacilityAlert | null; announce: boolean } {
  const contextId = facilityAlertContext(routeId, artifactVersion, temporalKey);
  const cooldownContext = JSON.stringify([routeId, artifactVersion, period]);
  const previous = previousState?.contextId === contextId ? previousState : null;
  const nextState: FacilityAlertState = { contextId, cooldownContext, activeId: null,
    announced: previousState?.cooldownContext === cooldownContext ? previousState.announced : {} };
  if (!enabled || period !== "night" || !Number.isFinite(progressM) || !artifactVersion ||
    localEnvironment?.artifact_version !== artifactVersion || localEnvironment.period !== period) {
    return { nextState, alert: null, announce: false };
  }
  const candidates = gapIntervals(routeEvidence).map(gap => ({
    ...gap, contextId, id: JSON.stringify([contextId, gap.kind, gap.startM, gap.endM]),
  })).sort((a, b) => Math.max(a.startM, progressM) - Math.max(b.startM, progressM));
  const visibleLength = (gap: Gap) => Math.min(gap.endM, progressM + policy.lookaheadM) - Math.max(progressM, gap.startM);
  const localSupport = ["lighting", "open_store"].some(factor => localEnvironment.factors[factor]?.state === "present");
  const allowed = (gap: Gap) => !localSupport || gap.startM - progressM > policy.startProximityM;
  const alert = candidates.find(gap => gap.id === previous?.activeId && allowed(gap) && visibleLength(gap) >= policy.clearM)
    ?? candidates.find(gap => allowed(gap) && visibleLength(gap) >= policy.triggerM) ?? null;
  if (!alert) return { nextState, alert, announce: false };
  nextState.activeId = alert.id;
  const cooldownId = JSON.stringify([alert.kind, alert.startM, alert.endM]);
  const announce = !localSupport && alert.startM - progressM <= policy.startProximityM && progressM < alert.endM
    && nowMs - (nextState.announced[cooldownId] ?? -Infinity) >= policy.cooldownMs;
  if (announce) nextState.announced = { ...nextState.announced, [cooldownId]: nowMs };
  return { nextState, alert, announce };
}

export function facilityAlertText(alert: FacilityAlert): string {
  return alert.kind === "lighting_and_store"
    ? "앞쪽 경로에 공개 자료상 조명·영업 시설 접근 공백이 있어요."
    : "앞쪽 경로에 공개 자료상 보안등 접근 공백이 있어요.";
}
