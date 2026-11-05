import type { DisplayMetric, FacilityZone, RoutePeriod, SafetyZone, ZoneLocation } from "./api";
import { readJson, writeJson } from "./preferences";
import { zoneDisplay, type DisplayZone } from "./zoneDisplay";

type Basis = {
  basis_id: string | null;
  artifact_version: string | null;
  model_version: string | null;
  policy_version: string | null;
  schedule_key: string | null;
};
export type WatchedZone = ZoneLocation & Basis & { metric: DisplayMetric; period: RoutePeriod | null; score: number | null };

const WATCHED_KEY = "ansim:watched-zones";
export const MAX_WATCHED_ZONES = 5;
const EMPTY_BASIS: Basis = { basis_id: null, artifact_version: null, model_version: null, policy_version: null, schedule_key: null };
const textOrNull = (value: unknown) => typeof value === "string" && value.length ? value : null;

function readZone(value: unknown, legacy: boolean): WatchedZone | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const { dong_code, dong_name, lat, lng, score, metric, period } = row;
  if (typeof dong_code !== "string" || typeof dong_name !== "string" || typeof lat !== "number"
    || typeof lng !== "number" || !Number.isFinite(lat) || !Number.isFinite(lng)
    || !(score === null && !legacy || typeof score === "number" && Number.isFinite(score))) return null;
  if (!legacy && metric !== "regional_statistics" && metric !== "facility_access") return null;
  return {
    dong_code, dong_name, lat, lng, score: score as number | null, metric: metric === "facility_access" && !legacy ? metric : "regional_statistics",
    period: !legacy && (period === "day" || period === "night") ? period : null,
    basis_id: textOrNull(row.basis_id), artifact_version: textOrNull(row.artifact_version),
    model_version: textOrNull(row.model_version), policy_version: textOrNull(row.policy_version), schedule_key: textOrNull(row.schedule_key),
  };
}

export function loadWatchedZones(): WatchedZone[] {
  const stored = readJson(WATCHED_KEY);
  const legacy = Array.isArray(stored);
  const current = stored && typeof stored === "object" && "schema" in stored && stored.schema === 2 && "zones" in stored ? stored.zones : null;
  const rows = legacy ? stored : current;
  return Array.isArray(rows) ? rows.map(row => readZone(row, legacy)).filter((row): row is WatchedZone => row !== null).slice(0, MAX_WATCHED_ZONES) : [];
}

export function saveWatchedZones(list: WatchedZone[]): void {
  writeJson(WATCHED_KEY, { schema: 2, zones: list.slice(0, MAX_WATCHED_ZONES) });
}

function watchedValue(zone: DisplayZone & { period?: RoutePeriod }, metric: DisplayMetric, period?: RoutePeriod): WatchedZone {
  const { dong_code, dong_name, lat, lng } = zone;
  const assessment = metric === "facility_access" ? zone.assessment : undefined;
  return { dong_code, dong_name, lat, lng, metric, period: period ?? zone.period ?? null, score: zoneDisplay(zone, metric).value,
    ...(assessment ? { basis_id: assessment.basis_id, artifact_version: assessment.artifact_version,
      model_version: assessment.model_version, policy_version: assessment.policy_version, schedule_key: assessment.schedule_key } : EMPTY_BASIS) };
}

export function toggleWatchedZone(zone: DisplayZone & { period?: RoutePeriod }, metric: DisplayMetric = "regional_statistics", period?: RoutePeriod): WatchedZone[] {
  const current = loadWatchedZones();
  const next = current.some(row => row.dong_code === zone.dong_code)
    ? current.filter(row => row.dong_code !== zone.dong_code)
    : current.length < MAX_WATCHED_ZONES ? [...current, watchedValue(zone, metric, period)] : current;
  saveWatchedZones(next);
  return next;
}

export function applyScoreChanges(watched: readonly WatchedZone[], latest: readonly SafetyZone[]) {
  const messages: string[] = [];
  const next = watched.map(w => {
    const current = latest.find(z => z.dong_code === w.dong_code);
    if (w.metric !== "regional_statistics" || !current) return w;
    const to = Math.round(current.safety_score);
    if (w.period === current.period && w.score !== null && Math.round(w.score) !== to) {
      const from = Math.round(w.score);
      messages.push(`${w.dong_name} 지역 통계 지수가 ${from}점에서 ${to}점으로 ${to > from ? "올랐" : "내려갔"}어요`);
    }
    return watchedValue(current, "regional_statistics");
  });
  return { next, messages };
}

export function applyFacilityScoreChanges(watched: readonly WatchedZone[], latest: readonly FacilityZone[], period: RoutePeriod) {
  const messages: string[] = [];
  const next = watched.map(w => {
    const current = latest.find(z => z.dong_code === w.dong_code);
    if (w.metric !== "facility_access" || w.period !== period || !current || current.assessment.status === "pending") return w;
    const replacement = watchedValue(current, "facility_access", period);
    const sameMeaning = w.basis_id && w.basis_id === replacement.basis_id && w.schedule_key === replacement.schedule_key
      && w.model_version === replacement.model_version && w.policy_version === replacement.policy_version;
    const newData = w.artifact_version && replacement.artifact_version && w.artifact_version !== replacement.artifact_version;
    if (sameMeaning && newData && w.score !== null && replacement.score !== null) {
      const from = Math.round(w.score), to = Math.round(replacement.score);
      if (from !== to) messages.push(`${w.dong_name} 공개 자료 기준 시설 점수가 ${from}점에서 ${to}점으로 바뀌었어요`);
    }
    return replacement;
  });
  return { next, messages };
}
