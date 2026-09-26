import assert from "node:assert/strict";
import test from "node:test";
import { runSmoke, validateSmokeConfig } from "./production-smoke.mjs";

const valid = {
  SMOKE_BASE_URL: "https://example.test",
  SMOKE_USER_EMAIL: "smoke@example.test",
  SMOKE_USER_PASSWORD: "not-printed",
  SMOKE_START_LAT: "37.5",
  SMOKE_START_LNG: "127.0",
  SMOKE_END_LAT: "37.51",
  SMOKE_END_LNG: "127.01",
};

test("requires an HTTPS origin without a path or port", () => {
  assert.equal(validateSmokeConfig(valid).base, "https://example.test");
  assert.throws(() => validateSmokeConfig({ ...valid, SMOKE_BASE_URL: "http://example.test" }));
  assert.throws(() => validateSmokeConfig({ ...valid, SMOKE_BASE_URL: "https://example.test:8000" }));
  assert.throws(() => validateSmokeConfig({ ...valid, SMOKE_BASE_URL: "https://example.test/api" }));
});

test("fails when the route endpoint returns a recoverable 422", async () => {
  const response = (status, body, cookies = []) => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    headers: { getSetCookie: () => cookies },
  });
  const fetch = async (url) => {
    if (url.endsWith("/health")) return response(200, { status: "ok" });
    if (url.endsWith("/auth/csrf")) return response(200, { csrf_token: "csrf" }, ["csrf_token=csrf; Secure"]);
    if (url.endsWith("/auth/login")) return response(200, {}, ["access_token=a; Secure; HttpOnly", "refresh_token=r; Secure; HttpOnly"]);
    if (url.endsWith("/auth/me")) return response(200, { email: valid.SMOKE_USER_EMAIL });
    if (url.includes("/safety/zones")) return response(200, [{ dong_code: "TEST" }]);
    return response(422, { detail: { reason: "safety_zones_unavailable" } });
  };

  await assert.rejects(runSmoke({ env: valid, fetch, log: () => {} }), /Route check failed/);
});

test("sends the CSRF token and accepts secure HttpOnly session cookies", async () => {
  const calls = [];
  const response = (body, cookies = []) => ({ ok: true, json: async () => body, headers: { getSetCookie: () => cookies } });
  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/health")) return response({ status: "ok" });
    if (url.endsWith("/auth/csrf")) return response({ csrf_token: "csrf" }, ["csrf_token=csrf; Secure"]);
    if (url.endsWith("/auth/login")) return response({}, ["access_token=a; Secure; HttpOnly", "refresh_token=r; Secure; HttpOnly"]);
    if (url.endsWith("/auth/me")) return response({ email: valid.SMOKE_USER_EMAIL });
    if (url.includes("/safety/zones")) return response([{ dong_code: "TEST" }]);
    return response({ mode: "straight_line", safety_score: 55, route_points: [{ lat: 37.5, lng: 127 }] });
  };

  await runSmoke({ env: valid, fetch, log: () => {} });
  const login = calls.find(({ url }) => url.endsWith("/auth/login"));
  assert.equal(login.options.headers["X-CSRF-Token"], "csrf");
  assert.match(login.options.headers.Cookie, /csrf_token=csrf/);
});
