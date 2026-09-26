const required = ["SMOKE_BASE_URL", "SMOKE_USER_EMAIL", "SMOKE_USER_PASSWORD", "SMOKE_START_LAT", "SMOKE_START_LNG", "SMOKE_END_LAT", "SMOKE_END_LNG"];

function config(env = process.env) {
  for (const name of required) if (!env[name]) throw new Error(`Missing ${name}`);
  const url = new URL(env.SMOKE_BASE_URL);
  if (url.protocol !== "https:" || url.pathname !== "/" || url.port) throw new Error("SMOKE_BASE_URL must be an HTTPS origin without a path or port");
  return { base: url.origin, email: env.SMOKE_USER_EMAIL, password: env.SMOKE_USER_PASSWORD, startLat: Number(env.SMOKE_START_LAT), startLng: Number(env.SMOKE_START_LNG), endLat: Number(env.SMOKE_END_LAT), endLng: Number(env.SMOKE_END_LNG) };
}

async function main() {
  const settings = config();
  const cookies = new Map();
  async function request(path, options = {}) {
    const response = await fetch(`${settings.base}/api${path}`, { ...options, headers: { ...options.headers, Cookie: [...cookies].map(([k, v]) => `${k}=${v}`).join("; ") } });
    for (const value of response.headers.getSetCookie?.() ?? []) {
      const [pair] = value.split(";"); const [name, cookie] = pair.split("="); cookies.set(name, cookie);
    }
    return response;
  }
  console.log("health");
  const health = await request("/health"); if (!health.ok || (await health.json()).status !== "ok") throw new Error("Health check failed");
  console.log("login");
  const csrf = await request("/auth/csrf"); const csrfBody = await csrf.json();
  const login = await request("/auth/login", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfBody.csrf_token }, body: JSON.stringify({ email: settings.email, password: settings.password, remember_me: false }) });
  const loginCookies = [...login.headers.getSetCookie?.() ?? []];
  const hasSecureHttpOnlyCookie = (name) => loginCookies.some((cookie) => cookie.startsWith(`${name}=`) && cookie.includes("Secure") && cookie.includes("HttpOnly"));
  if (!login.ok || !hasSecureHttpOnlyCookie("access_token") || !hasSecureHttpOnlyCookie("refresh_token")) throw new Error("Login cookie check failed");
  const me = await request("/auth/me"); if (!me.ok || (await me.json()).email !== settings.email) throw new Error("Session check failed");
  console.log("safety");
  const zones = await request(`/safety/zones?lat=${settings.startLat}&lng=${settings.startLng}&radius_km=2`); if (!zones.ok || !(await zones.json()).length) throw new Error("Zone check failed");
  const route = await request("/safety/route", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfBody.csrf_token }, body: JSON.stringify({ start_lat: settings.startLat, start_lng: settings.startLng, end_lat: settings.endLat, end_lng: settings.endLng }) });
  const body = await route.json(); if (!route.ok || !["safety_weighted", "tmap", "straight_line"].includes(body.mode) || !body.route_points?.length || !Number.isFinite(body.safety_score)) throw new Error("Route check failed");
}

main().catch((error) => { console.error(error.message); process.exitCode = 1; });
