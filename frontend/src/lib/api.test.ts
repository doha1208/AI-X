import { afterEach, expect, test, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

test("uses the same-origin api proxy when no override is configured", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  delete process.env.NEXT_PUBLIC_API_BASE_URL;

  const { nearbyZones } = await import("./api");
  await nearbyZones(37.5, 127, 2);

  expect(fetch).toHaveBeenCalledWith(
    "/api/safety/zones?lat=37.5&lng=127&radius_km=2",
    expect.objectContaining({ credentials: "include" }),
  );
});

test("refreshes an expired access token when checking the session on page load", async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response("{}", { status: 401 })) // /auth/me with expired token
    .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "t" }), { status: 200 })) // /auth/csrf
    .mockResolvedValueOnce(new Response("{}", { status: 200 })) // /auth/refresh
    .mockResolvedValueOnce(new Response(JSON.stringify({ email: "a@b.c" }), { status: 200 })); // /auth/me retry
  vi.stubGlobal("fetch", fetch);

  const { me } = await import("./api");

  await expect(me()).resolves.toEqual({ email: "a@b.c" });
  expect(fetch.mock.calls.map(([url]) => url)).toEqual(["/api/auth/me", "/api/auth/csrf", "/api/auth/refresh", "/api/auth/me"]);
});

test("shows the readable message from a FastAPI validation error", async () => {
  const detail = [{ type: "value_error", msg: "Value error, 직선거리 10km를 초과하는 보행 경로는 지원하지 않습니다" }];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 })));

  const { nearbyZones } = await import("./api");

  await expect(nearbyZones(37.5, 127, 2)).rejects.toThrow("직선거리 10km를 초과하는 보행 경로는 지원하지 않습니다");
});
