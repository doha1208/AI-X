import { beforeEach, describe, expect, it } from "vitest";
import {
  addNotification,
  clearNotifications,
  loadNotifications,
  markAllRead,
  syncNotices,
  unreadCount,
} from "./notifications";

beforeEach(() => localStorage.clear());

describe("notifications", () => {
  it("keeps the newest first and caps the log at 30", () => {
    for (let i = 0; i < 32; i++) addNotification("caution", `구역 ${i}`, 1000 + i);

    const list = loadNotifications();
    expect(list).toHaveLength(30);
    expect(list[0].text).toBe("구역 31");
    expect(list[29].text).toBe("구역 2");
  });

  it("counts unread ones and clears the count when marked read", () => {
    addNotification("caution", "a");
    addNotification("score", "b");
    expect(unreadCount(loadNotifications())).toBe(2);

    markAllRead();
    expect(unreadCount(loadNotifications())).toBe(0);
    expect(loadNotifications()).toHaveLength(2);
  });

  it("empties the log on clear", () => {
    addNotification("caution", "a");
    clearNotifications();
    expect(loadNotifications()).toEqual([]);
  });

  it("drops malformed stored entries instead of crashing", () => {
    localStorage.setItem(
      "ansim:notifications",
      JSON.stringify([{ text: "id 없음" }, { id: "1", kind: "caution", text: "정상", at: 1, read: false }, 7])
    );
    expect(loadNotifications().map((n) => n.text)).toEqual(["정상"]);
  });

  it("adds each notice once, however often it is synced", () => {
    const notices = [
      { id: "n1", text: "첫 공지", at: 100 },
      { id: "n2", text: "둘째 공지", at: 200 },
    ];
    syncNotices(notices);
    syncNotices(notices);

    const list = loadNotifications();
    expect(list.map((n) => n.text)).toEqual(["둘째 공지", "첫 공지"]);
    expect(list.every((n) => n.kind === "notice")).toBe(true);
  });

  it("does not bring a notice back after the log was cleared", () => {
    syncNotices([{ id: "n1", text: "공지", at: 1 }]);
    clearNotifications();
    syncNotices([{ id: "n1", text: "공지", at: 1 }]);
    expect(loadNotifications()).toEqual([]);
  });
});
