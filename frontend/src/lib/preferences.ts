export type TimeMode = "auto" | "day" | "night";
// voiceVolume: 길안내 음성 음량(0~1). keepScreenOn: 길안내 중 화면이 꺼지지 않게 할지.
export type Settings = {
  showBells: boolean;
  timeMode: TimeMode;
  voiceOn: boolean;
  voiceVolume: number;
  keepScreenOn: boolean;
};
// lat/lng을 함께 저장해서, 다시 고를 때 이름으로 재검색하지 않고 바로 그 위치로 간다
// (동명 지명이나 지오코딩 실패로 엉뚱한 곳이 잡히는 걸 막는다).
export type RecentEntry = { label: string; lat: number; lng: number; at: number };
export type RecentPlace = { label: string; lat: number; lng: number };
export type RecentKind = "searches" | "destinations";

const SETTINGS_KEY = "ansim:settings";
const RECENT_KEYS: Record<RecentKind, string> = {
  searches: "ansim:recent-searches",
  destinations: "ansim:recent-destinations",
};
const MAX_RECENT = 5;
const TIME_MODES: TimeMode[] = ["auto", "day", "night"];

// SOS에서 위치 문자를 보낼 보호자 연락처. 서버에 올리지 않고 이 기기에만 저장한다.
export type EmergencyContact = { name: string; phone: string };
const EMERGENCY_CONTACTS_KEY = "ansim:emergency-contacts";
const MAX_EMERGENCY_CONTACTS = 3;

export const DEFAULT_SETTINGS: Settings = {
  showBells: true,
  timeMode: "auto",
  voiceOn: true,
  voiceVolume: 0.8,
  keepScreenOn: false,
};

// 서버 렌더링·사생활 보호 모드처럼 localStorage를 못 쓰는 환경에서는 기본값으로 동작한다.
export function readJson(key: string): unknown {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장 실패는 조용히 무시한다 — 이 값들은 편의 기능일 뿐이다.
  }
}

export function loadSettings(): Settings {
  const stored = readJson(SETTINGS_KEY);
  if (!stored || typeof stored !== "object") return DEFAULT_SETTINGS;
  const { showBells, timeMode, voiceOn, voiceVolume, keepScreenOn } = stored as Partial<Record<keyof Settings, unknown>>;
  const validVolume = typeof voiceVolume === "number" && voiceVolume >= 0 && voiceVolume <= 1;
  return {
    showBells: typeof showBells === "boolean" ? showBells : DEFAULT_SETTINGS.showBells,
    timeMode: TIME_MODES.includes(timeMode as TimeMode) ? (timeMode as TimeMode) : DEFAULT_SETTINGS.timeMode,
    voiceOn: typeof voiceOn === "boolean" ? voiceOn : DEFAULT_SETTINGS.voiceOn,
    voiceVolume: validVolume ? voiceVolume : DEFAULT_SETTINGS.voiceVolume,
    keepScreenOn: typeof keepScreenOn === "boolean" ? keepScreenOn : DEFAULT_SETTINGS.keepScreenOn,
  };
}

export function saveSettings(settings: Settings): void {
  writeJson(SETTINGS_KEY, settings);
}

function isRecentEntry(value: unknown): value is RecentEntry {
  if (!value || typeof value !== "object") return false;
  const { label, lat, lng, at } = value as Record<string, unknown>;
  return typeof label === "string" && typeof lat === "number" && typeof lng === "number" && typeof at === "number";
}

export function loadRecent(kind: RecentKind): RecentEntry[] {
  const stored = readJson(RECENT_KEYS[kind]);
  // 좌표 없이 저장된 옛 기록(label만 있던 버전)은 걸러낸다 — 없는 값을 채워 넣기보다는
  // 다시 검색해서 새로 쌓이게 두는 편이 안전하다.
  return Array.isArray(stored) ? stored.filter(isRecentEntry).slice(0, MAX_RECENT) : [];
}

export function addRecent(kind: RecentKind, place: RecentPlace): void {
  const trimmed = place.label.trim();
  if (!trimmed) return;
  const rest = loadRecent(kind).filter((entry) => entry.label !== trimmed);
  const entry: RecentEntry = { label: trimmed, lat: place.lat, lng: place.lng, at: Date.now() };
  writeJson(RECENT_KEYS[kind], [entry, ...rest].slice(0, MAX_RECENT));
}

// 서버는 시각만 보고 낮(06~22시)/밤을 가르므로, 고정 시각을 보내 가중치를 강제한다.
export function routeTimeFor(mode: TimeMode): string | undefined {
  if (mode === "day") return "2000-01-01T12:00:00+09:00";
  if (mode === "night") return "2000-01-01T23:00:00+09:00";
  return undefined;
}

// sms: 링크에 그대로 들어가므로 숫자·+·-·공백·괄호만 허용하고 숫자가 3자리 이상일 때만 번호로 본다.
export function isValidPhone(phone: string): boolean {
  return /^[\d+\-\s()]+$/.test(phone) && phone.replace(/\D/g, "").length >= 3;
}

function isEmergencyContact(value: unknown): value is EmergencyContact {
  if (!value || typeof value !== "object") return false;
  const { name, phone } = value as Record<string, unknown>;
  return typeof name === "string" && typeof phone === "string" && isValidPhone(phone);
}

export function loadEmergencyContacts(): EmergencyContact[] {
  const stored = readJson(EMERGENCY_CONTACTS_KEY);
  return Array.isArray(stored) ? stored.filter(isEmergencyContact).slice(0, MAX_EMERGENCY_CONTACTS) : [];
}

export function saveEmergencyContacts(contacts: EmergencyContact[]): void {
  writeJson(EMERGENCY_CONTACTS_KEY, contacts.slice(0, MAX_EMERGENCY_CONTACTS));
}
