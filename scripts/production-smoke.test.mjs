import assert from "node:assert/strict";
import test from "node:test";
import { runSmoke, validateSmokeConfig, classifyRoute } from "./production-smoke.mjs";

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
    if (url.endsWith("/health")) return response(200, { status: "ok", route_artifact: { area_environment_ready: true, zone_environment_ready: true }, facility_assessment: { applied: true } });
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
    if (url.endsWith("/health")) return response({ status: "ok", route_artifact: { area_environment_ready: true, zone_environment_ready: true }, facility_assessment: { applied: true } });
    if (url.endsWith("/auth/csrf")) return response({ csrf_token: "csrf" }, ["csrf_token=csrf; Secure"]);
    if (url.endsWith("/auth/login")) return response({}, ["access_token=a; Secure; HttpOnly", "refresh_token=r; Secure; HttpOnly"]);
    if (url.endsWith("/auth/me")) return response({ email: valid.SMOKE_USER_EMAIL });
    if (url.includes("/safety/zones")) return response([{ dong_code: "TEST" }]);
    return response(walking());
  };

  await runSmoke({ env: valid, fetch, log: () => {} });
  const login = calls.find(({ url }) => url.endsWith("/auth/login"));
  assert.equal(login.options.headers["X-CSRF-Token"], "csrf");
  assert.match(login.options.headers.Cookie, /csrf_token=csrf/);
});

function walking(assessment = { evaluation_basis: "unavailable", score: null, used_factors: [] }) {
  return { mode: "tmap", safety_score: null, environment_model_applied: true,
    route_points: [{ lat: 37.5, lng: 127 }, { lat: 37.501, lng: 127 }], environment_assessment: assessment };
}

test("distinguishes unavailable, walkable-only, and assessed routes without the retired scalar", () => {
  assert.equal(classifyRoute({ detail: { reason: "pedestrian_route_unavailable" } }, 503), "unavailable");
  assert.equal(classifyRoute(walking(), 200), "walkable_only");
  assert.equal(classifyRoute(walking({ evaluation_basis: "single_factor", score: null, reference_score: 0, reference_factor: "bell", used_factors: ["bell"] }), 200), "assessed");
  assert.equal(classifyRoute(walking({ evaluation_basis: "multi_factor", score: 0, used_factors: ["bell", "cctv"] }), 200), "assessed");
  assert.equal(classifyRoute(walking({ evaluation_basis: "partial_coverage", score: null, score_bounds: { lower: 10, upper: 90 }, used_factors: [] }), 200), "walkable_only");
  for (const malformed of [{ ...walking(), mode: "straight_line" }, { ...walking(), safety_score: 50 },
    { ...walking(), route_points: [{ lat: 37.5, lng: 127 }] },
    walking({ evaluation_basis: "multi_factor", score: null, used_factors: ["bell", "cctv"] }),
    walking({ evaluation_basis: "unavailable", score: 0 })]) {
    assert.throws(() => classifyRoute(malformed, 200), /Route check failed/);
  }
});
