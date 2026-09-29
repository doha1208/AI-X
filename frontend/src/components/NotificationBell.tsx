"use client";

import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { BellIcon } from "@/components/icons";
import { NOTICES } from "@/lib/notices";
import {
  clearNotifications,
  markAllRead,
  parseNotifications,
  readNotificationsRaw,
  subscribeNotifications,
  syncNotices,
  unreadCount,
  type NotificationKind,
} from "@/lib/notifications";
import styles from "./NotificationBell.module.css";

const KIND_LABEL: Record<NotificationKind, string> = { caution: "주의 구역", score: "안전지수", notice: "공지" };

function formatTime(at: number): string {
  return new Date(at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const serverSnapshot = () => "";

export function NotificationBell() {
  const raw = useSyncExternalStore(subscribeNotifications, readNotificationsRaw, serverSnapshot);
  const list = useMemo(() => parseNotifications(raw), [raw]);
  const unread = unreadCount(list);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    syncNotices(NOTICES);
  }, []);

  // 패널을 닫을 때 읽음 처리한다 — 열려 있는 동안은 새 알림이 강조된 채로 남는다.
  function close() {
    setOpen(false);
    markAllRead();
  }

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (!rootRef.current?.contains(e.target as Node)) close();
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        type="button"
        className={styles.button}
        aria-label={unread > 0 ? `알림 (읽지 않은 알림 ${unread}개)` : "알림"}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <BellIcon size={18} />
        {unread > 0 && <span className={styles.badge}>{unread}</span>}
      </button>

      {open && (
        <section id={panelId} className={styles.panel} aria-label="알림 목록">
          <header className={styles.header}>
            <h2 className={styles.title}>알림</h2>
            {list.length > 0 && (
              <button type="button" className={styles.clear} onClick={clearNotifications}>
                모두 지우기
              </button>
            )}
          </header>
          {list.length === 0 ? (
            <p className={styles.empty}>새 알림이 없어요.</p>
          ) : (
            <ul className={styles.list}>
              {list.map((item) => (
                <li key={item.id} className={`${styles.item} ${item.read ? "" : styles.itemUnread}`}>
                  <span className={styles.kind}>{KIND_LABEL[item.kind]}</span>
                  <p className={styles.text}>{item.text}</p>
                  <time className={styles.time} dateTime={new Date(item.at).toISOString()}>
                    {formatTime(item.at)}
                  </time>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
