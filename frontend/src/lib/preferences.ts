export type TimeMode = "auto" | "day" | "night";
// voiceVolume: 길안내 음성 음량(0~1).
export type Settings = { showBells: boolean; timeMode: TimeMode; voiceOn: boolean; voiceVolume: number };
export type RecentEntry = { label: string; at: number };
export type RecentKind = "searches" | "destinations";

const SETTINGS_KEY = "ansim:settings";
const RECENT_KEYS: Record<RecentKind, string> = {
  searches: "ansim:recent-searches",
  destinations: "ansim:recent-destinations",
};
const MAX_RECENT = 5;
const TIME_MODES: TimeMode[] = ["auto", "day", "night"];

export const DEFAULT_SETTINGS: Settings = { showBells: true, timeMode: "auto", voiceOn: true, voiceVolume: 0.8 };

// 서버 렌더링·사생활 보호 모드처럼 localStorage를 못 쓰는 환경에서는 기본값으로 동작한다.
function readJson(key: string): unknown {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장 실패는 조용히 무시한다 — 이 값들은 편의 기능일 뿐이다.
  }
}

export function loadSettings(): Settings {
  const stored = readJson(SETTINGS_KEY);
  if (!stored || typeof stored !== "object") return DEFAULT_SETTINGS;
  const { showBells, timeMode, voiceOn, voiceVolume } = stored as Partial<Record<keyof Settings, unknown>>;
  const validVolume = typeof voiceVolume === "number" && voiceVolume >= 0 && voiceVolume <= 1;
  return {
    showBells: typeof showBells === "boolean" ? showBells : DEFAULT_SETTINGS.showBells,
    timeMode: TIME_MODES.includes(timeMode as TimeMode) ? (timeMode as TimeMode) : DEFAULT_SETTINGS.timeMode,
    voiceOn: typeof voiceOn === "boolean" ? voiceOn : DEFAULT_SETTINGS.voiceOn,
    voiceVolume: validVolume ? voiceVolume : DEFAULT_SETTINGS.voiceVolume,
  };
}

export function saveSettings(settings: Settings): void {
  writeJson(SETTINGS_KEY, settings);
}

function isRecentEntry(value: unknown): value is RecentEntry {
  if (!value || typeof value !== "object") return false;
  const { label, at } = value as Record<string, unknown>;
  return typeof label === "string" && typeof at === "number";
}

export function loadRecent(kind: RecentKind): RecentEntry[] {
  const stored = readJson(RECENT_KEYS[kind]);
  return Array.isArray(stored) ? stored.filter(isRecentEntry).slice(0, MAX_RECENT) : [];
}

export function addRecent(kind: RecentKind, label: string): void {
  const trimmed = label.trim();
  if (!trimmed) return;
  const rest = loadRecent(kind).filter((entry) => entry.label !== trimmed);
  writeJson(RECENT_KEYS[kind], [{ label: trimmed, at: Date.now() }, ...rest].slice(0, MAX_RECENT));
}

// 서버는 시각만 보고 낮(06~22시)/밤을 가르므로, 고정 시각을 보내 가중치를 강제한다.
export function routeTimeFor(mode: TimeMode): string | undefined {
  if (mode === "day") return "2000-01-01T12:00:00+09:00";
  if (mode === "night") return "2000-01-01T23:00:00+09:00";
  return undefined;
}
