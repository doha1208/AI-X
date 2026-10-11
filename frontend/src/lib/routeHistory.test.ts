import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearRouteHistory, getRouteHistory, saveRouteHistory, setRouteHistoryRemember } from "./api";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function response(body: unknown, status = 200) {
  return { ok: status < 300, status, json: async () => body };
}

beforeEach(() => fetchMock.mockReset());

describe("route history API", () => {
  it("reads history without a CSRF request", async () => {
    fetchMock.mockResolvedValueOnce(response({ remember_route_history: true, items: [] }));
    await expect(getRouteHistory()).resolves.toEqual({ rememberRouteHistory: true, items: [] });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/me/route-history");
  });

  it("uses CSRF for save, settings and delete", async () => {
    fetchMock
      .mockResolvedValueOnce(response({ csrf_token: "csrf" }))
      .mockResolvedValueOnce(response({ remember_route_history: true, items: [] }))
      .mockResolvedValueOnce(response({ csrf_token: "csrf" }))
      .mockResolvedValueOnce(response({ remember_route_history: false, items: [] }))
      .mockResolvedValueOnce(response({ csrf_token: "csrf" }))
      .mockResolvedValueOnce({ ok: true, status: 204, json: async () => ({}) });
    const place = { label: "집", lat: 37.5, lng: 127 };
    await saveRouteHistory(place, { label: "역", lat: 37.6, lng: 127.1 });
    await setRouteHistoryRemember(false);
    await clearRouteHistory();
    const unsafe = fetchMock.mock.calls.filter((call) => call[1]?.method && call[1].method !== "GET");
    expect(unsafe).toHaveLength(3);
    unsafe.forEach((call) => expect(call[1].headers.get("X-CSRF-Token")).toBe("csrf"));
  });
});
