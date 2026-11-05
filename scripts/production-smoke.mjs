import { fileURLToPath } from "node:url";

const required = ["SMOKE_BASE_URL", "SMOKE_USER_EMAIL", "SMOKE_USER_PASSWORD", "SMOKE_START_LAT", "SMOKE_START_LNG", "SMOKE_END_LAT", "SMOKE_END_LNG"];

export function validateSmokeConfig(env = process.env) {
  for (const name of required) if (!env[name]) throw new Error(`Missing ${name}`);
  const url = new URL(env.SMOKE_BASE_URL);
  if (url.protocol !== "https:" || url.pathname !== "/" || url.port) throw new Error("SMOKE_BASE_URL must be an HTTPS origin without a path or port");
  return { base: url.origin, email: env.SMOKE_USER_EMAIL, password: env.SMOKE_USER_PASSWORD, startLat: Number(env.SMOKE_START_LAT), startLng: Number(env.SMOKE_START_LNG), endLat: Number(env.SMOKE_END_LAT), endLng: Number(env.SMOKE_END_LNG) };
}

export function classifyRoute(body, status) {
  if (status === 503 && body.detail?.reason === "pedestrian_route_unavailable") return "unavailable";
  const fail = () => { throw new Error("Route check failed"); };
  if (status !== 200 || !["safety_weighted", "tmap"].includes(body.mode) || body.safety_score !== null ||
      body.environment_model_applied !== true || !Array.isArray(body.route_points) || body.route_points.length < 2 ||
      !body.route_points.every((p) => Number.isFinite(p.lat) && Math.abs(p.lat) <= 90 && Number.isFinite(p.lng) && Math.abs(p.lng) <= 180) ||
      !body.route_points.some((p) => p.lat !== body.route_points[0].lat || p.lng !== body.route_points[0].lng)) fail();
  const a = body.environment_assessment;
  const score = (value) => Number.isFinite(value) && value >= 0 && value <= 100;
  if (!a) fail();
  if (a.evaluation_basis === "multi_factor") {
    if (!score(a.score) || new Set(a.used_factors).size < 2) fail();
    return "assessed";
  }
  if (a.score !== null) fail();
  if (a.evaluation_basis === "single_factor") {
    if (!score(a.reference_score) || a.used_factors?.length !== 1 || a.used_factors[0] !== a.reference_factor) fail();
    return "assessed";
  }
  if (!["partial_coverage", "observed_only", "unavailable"].includes(a.evaluation_basis)) fail();
  if (a.evaluation_basis === "partial_coverage" && (!score(a.score_bounds?.lower) || !score(a.score_bounds?.upper) || a.score_bounds.lower > a.score_bounds.upper)) fail();
  return "walkable_only";
}

export async function runSmoke({ env = process.env, fetch = globalThis.fetch, log = console.log } = {}) {
  const settings = validateSmokeConfig(env);
  const cookies = new Map();
  async function request(path, options = {}) {
    const response = await fetch(`${settings.base}/api${path}`, { ...options, headers: { ...options.headers, Cookie: [...cookies].map(([k, v]) => `${k}=${v}`).join("; ") } });
    for (const value of response.headers.getSetCookie?.() ?? []) {
      const [pair] = value.split(";"); const [name, cookie] = pair.split("="); cookies.set(name, cookie);
    }
    return response;
  }
  log("health");
  const health = await request("/health"); const readiness = await health.json();
  if (!health.ok || readiness.status !== "ok") throw new Error("Health check failed");
  if (!readiness.facility_assessment?.applied || !readiness.route_artifact?.area_environment_ready || !readiness.route_artifact?.zone_environment_ready) throw new Error("Facility artifact not ready");
  log("facility artifact ready");
  log("login");
  const csrf = await request("/auth/csrf"); const csrfBody = await csrf.json();
  const login = await request("/auth/login", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfBody.csrf_token }, body: JSON.stringify({ email: settings.email, password: settings.password, remember_me: false }) });
  const loginCookies = [...login.headers.getSetCookie?.() ?? []];
  const hasSecureHttpOnlyCookie = (name) => loginCookies.some((cookie) => cookie.startsWith(`${name}=`) && cookie.includes("Secure") && cookie.includes("HttpOnly"));
  if (!login.ok || !hasSecureHttpOnlyCookie("access_token") || !hasSecureHttpOnlyCookie("refresh_token")) throw new Error("Login cookie check failed");
  const me = await request("/auth/me"); if (!me.ok || (await me.json()).email !== settings.email) throw new Error("Session check failed");
  log("safety");
  const zones = await request(`/safety/zones?lat=${settings.startLat}&lng=${settings.startLng}&radius_km=2`); if (!zones.ok || !(await zones.json()).length) throw new Error("Zone check failed");
  const route = await request("/safety/route", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfBody.csrf_token }, body: JSON.stringify({ start_lat: settings.startLat, start_lng: settings.startLng, end_lat: settings.endLat, end_lng: settings.endLng }) });
  const body = await route.json(); const routeState = classifyRoute(body, route.status ?? (route.ok ? 200 : 500));
  log(`route: ${routeState}`);
  if (routeState === "unavailable") throw new Error("Route check failed: pedestrian route unavailable");
  return { route: routeState, artifact_version: readiness.facility_assessment.artifact_version };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  runSmoke().catch((error) => { console.error(error.message); process.exitCode = 1; });
}
