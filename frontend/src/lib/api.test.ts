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
