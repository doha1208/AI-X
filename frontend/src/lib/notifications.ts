import { readJson, writeJson } from "./preferences";

export type NotificationKind = "caution" | "score" | "notice";
export type AppNotification = { id: string; kind: NotificationKind; text: string; at: number; read: boolean };
export type Notice = { id: string; text: string; at: number };

const NOTIFICATIONS_KEY = "ansim:notifications";
const SEEN_NOTICES_KEY = "ansim:seen-notices";
const MAX_NOTIFICATIONS = 30;
// 같은 탭 안에서는 storage 이벤트가 오지 않으므로 직접 알려서 헤더의 종 배지가 바로 갱신되게 한다.
const CHANGED_EVENT = "ansim:notifications-changed";

const KINDS: NotificationKind[] = ["caution", "score", "notice"];

function isNotification(value: unknown): value is AppNotification {
  if (!value || typeof value !== "object") return false;
  const { id, kind, text, at, read } = value as Record<string, unknown>;
  return (
    typeof id === "string" &&
    KINDS.includes(kind as NotificationKind) &&
    typeof text === "string" &&
    typeof at === "number" &&
    typeof read === "boolean"
  );
}

export function parseNotifications(raw: string): AppNotification[] {
  try {
    const stored: unknown = raw ? JSON.parse(raw) : null;
    return Array.isArray(stored) ? stored.filter(isNotification).slice(0, MAX_NOTIFICATIONS) : [];
  } catch {
    return [];
  }
}

export function loadNotifications(): AppNotification[] {
  return parseNotifications(readNotificationsRaw());
}

function save(list: AppNotification[]): void {
  writeJson(NOTIFICATIONS_KEY, list.slice(0, MAX_NOTIFICATIONS));
  if (typeof window !== "undefined") window.dispatchEvent(new Event(CHANGED_EVENT));
}

export function addNotification(kind: NotificationKind, text: string, now: number = Date.now()): void {
  const id = `${now}-${Math.random().toString(36).slice(2, 8)}`;
  save([{ id, kind, text, at: now, read: false }, ...loadNotifications()]);
}

export function unreadCount(list: readonly AppNotification[]): number {
  return list.filter((n) => !n.read).length;
}

export function markAllRead(): void {
  const list = loadNotifications();
  if (unreadCount(list) === 0) return;
  save(list.map((n) => ({ ...n, read: true })));
}

export function clearNotifications(): void {
  save([]);
}

// 공지는 처음 본 것만 알림으로 넣는다 — 이미 넣은 공지는 비운 뒤에도 되살리지 않는다.
export function syncNotices(notices: readonly Notice[]): void {
  const stored = readJson(SEEN_NOTICES_KEY);
  const seen = Array.isArray(stored) ? stored.filter((id): id is string => typeof id === "string") : [];
  const fresh = notices.filter((n) => !seen.includes(n.id));
  if (fresh.length === 0) return;
  writeJson(SEEN_NOTICES_KEY, [...seen, ...fresh.map((n) => n.id)]);
  const added: AppNotification[] = fresh.map((n) => ({
    id: `notice-${n.id}`,
    kind: "notice",
    text: n.text,
    at: n.at,
    read: false,
  }));
  save([...added, ...loadNotifications()].sort((a, b) => b.at - a.at));
}

// useSyncExternalStore용 — 원본 문자열이 그대로면 같은 값이라 불필요한 재렌더가 없다.
export function readNotificationsRaw(): string {
  try {
    return localStorage.getItem(NOTIFICATIONS_KEY) ?? "";
  } catch {
    return "";
  }
}

export function subscribeNotifications(onChange: () => void): () => void {
  window.addEventListener(CHANGED_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGED_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
