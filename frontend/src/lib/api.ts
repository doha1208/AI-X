// 배포 기본값은 동일 출처 프록시다. 로컬에서는 .env.local로 localhost:8000을 지정한다.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;
let refreshRequest: Promise<boolean> | null = null;

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  // FastAPI 입력 검증 오류: [{ msg: "Value error, 직선거리 10km를 ..." }] — 사람이 읽을 문구만 꺼낸다.
  const first: unknown = Array.isArray(detail) ? detail[0] : undefined;
  if (first && typeof first === "object" && "msg" in first && typeof first.msg === "string") {
    return first.msg.replace(/^Value error, /, "");
  }
  if (detail && typeof detail === "object" && "action" in detail && typeof detail.action === "string") {
    return detail.action;
  }
  return fallback;
}

export type SafetyZone = {
  dong_code: string;
  dong_name: string;
  lat: number;
  lng: number;
  safety_score: number;
  day_safety_score: number;
  night_safety_score: number;
  period: RoutePeriod;
};

export type RouteMode = "safety_weighted" | "tmap";
export type RoutePeriod = "day" | "night";
export type RouteDataBasis = "zone_safety_indicators" | "osm_walking_network" | "facility_density" | "tmap_pedestrian_route";
export type RouteMissingDataFactor = "streetlight_data" | "crime_rate" | "police_distance" | "emergency_bell_distance" | "accident_hotspot_distance";
export type RouteFallbackReason = "none" | "safety_weighted_unavailable";

export type RouteDataDisclosure = {
  data_basis: RouteDataBasis[];
  // 원본 공공데이터의 날짜가 아니라 검증된 경로 산출물이 게시된 시각이다.
  updated_at: string | null;
  missing_data: { factor: RouteMissingDataFactor; affected_zone_count: number }[];
  fallback: { applied: boolean; mode: RouteMode; reason: RouteFallbackReason };
};

export type RouteResult = {
  safety_score: number;
  zones_passed: SafetyZone[];
  route_points: { lat: number; lng: number }[];
  mode: RouteMode;
  // timeMode가 자동일 때 실제로 어느 시간대 가중치가 쓰였는지 — "야간 기준" 배지에 쓴다.
  period: RoutePeriod;
  data_disclosure: RouteDataDisclosure;
  alternatives: RouteAlternative[];
  shortest_route_points: { lat: number; lng: number }[] | null;
  shortest_zones_passed?: SafetyZone[] | null;
};

export type RouteAlternative = {
  route_points: { lat: number; lng: number }[];
  safety_score: number;
  distance_m: number;
  zones_passed: SafetyZone[];
};

export type User = { id: number; email: string };
export type RouteHistoryPlace = { label: string; lat: number; lng: number };
export type RouteHistoryItem = { start: RouteHistoryPlace; end: RouteHistoryPlace; lastUsedAt: string };
export type RouteHistorySnapshot = { rememberRouteHistory: boolean; items: RouteHistoryItem[] };

export type ScoreWeights = Record<"day" | "night", Record<string, number>>;

export type ScoringProfile = {
  id: number;
  version: string;
  name: string;
  description: string | null;
  weights: ScoreWeights;
  unknown_score: number;
  status: "draft" | "active";
  created_at: string;
  created_by: string;
};

export type ScoreBuild = {
  id: number;
  profile_id: number;
  profile_version: string;
  status: "queued" | "building" | "succeeded" | "failed";
  artifact_version: string | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ScoringProfileDraft = Pick<ScoringProfile, "version" | "name" | "description" | "weights" | "unknown_score">;

function isUnsafeMethod(method?: string) {
  return !["GET", "HEAD", "OPTIONS"].includes((method ?? "GET").toUpperCase());
}

async function ensureCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  if (!csrfRequest) {
    csrfRequest = fetch(`${API_BASE}/auth/csrf`, { credentials: "include", cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("CSRF 토큰을 가져오지 못했습니다.");
        const body = await response.json() as { csrf_token: string };
        csrfToken = body.csrf_token;
        return csrfToken;
      })
      .finally(() => { csrfRequest = null; });
  }
  return csrfRequest;
}

async function refreshAccess(): Promise<boolean> {
  if (!refreshRequest) {
    refreshRequest = (async () => {
      const token = await ensureCsrfToken();
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": token },
      });
      csrfToken = null;
      return response.ok;
    })().finally(() => { refreshRequest = null; });
  }
  return refreshRequest;
}

async function request<T>(path: string, options: RequestInit = {}, retried = false): Promise<T> {
  const unsafe = isUnsafeMethod(options.method);
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (unsafe) headers.set("X-CSRF-Token", await ensureCsrfToken());
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers,
  });
  if (unsafe) csrfToken = null;
  // 로그인·갱신 요청 자체는 다시 갱신하지 않는다. /auth/me는 새로고침마다 부르므로 만료된 access token을 여기서 갱신해야 한다.
  const canRefresh = path === "/auth/me" || !path.startsWith("/auth/");
  if (res.status === 401 && !retried && canRefresh) {
    if (await refreshAccess()) return request<T>(path, options, true);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(errorMessage(body.detail, `Request failed: ${res.status}`));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function signup(email: string, password: string) {
  return request("/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function login(email: string, password: string, rememberMe: boolean) {
  return request<User>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, remember_me: rememberMe }),
  });
}

export function me() {
  return request<User>("/auth/me");
}

export function logout() {
  return request<void>("/auth/logout", { method: "POST" });
}

function routeHistorySnapshot(value: { remember_route_history: boolean; items: { start: RouteHistoryPlace; end: RouteHistoryPlace; last_used_at: string }[] }): RouteHistorySnapshot {
  return { rememberRouteHistory: value.remember_route_history, items: value.items.map((item) => ({ start: item.start, end: item.end, lastUsedAt: item.last_used_at })) };
}

export async function getRouteHistory(): Promise<RouteHistorySnapshot> {
  return routeHistorySnapshot(await request("/me/route-history"));
}

export async function saveRouteHistory(start: RouteHistoryPlace, end: RouteHistoryPlace): Promise<RouteHistorySnapshot> {
  return routeHistorySnapshot(await request("/me/route-history", { method: "POST", body: JSON.stringify({ start, end }) }));
}

export async function setRouteHistoryRemember(remember_route_history: boolean): Promise<RouteHistorySnapshot> {
  return routeHistorySnapshot(await request("/me/route-history/settings", { method: "PATCH", body: JSON.stringify({ remember_route_history }) }));
}

export function clearRouteHistory(): Promise<void> {
  return request("/me/route-history", { method: "DELETE" });
}

export function residenceRecommend(limit = 5) {
  return request<SafetyZone[]>(`/safety/residence-recommend?limit=${limit}`);
}

export function nearbyZones(lat: number, lng: number, radiusKm = 2) {
  return request<SafetyZone[]>(
    `/safety/zones?lat=${lat}&lng=${lng}&radius_km=${radiusKm}`
  );
}

export function nearbyBells(lat: number, lng: number, radiusKm = 1, limit?: number, options: RequestInit = {}) {
  const limitParam = limit ? `&limit=${limit}` : "";
  return request<{ lat: number; lng: number }[]>(`/safety/bells?lat=${lat}&lng=${lng}&radius_km=${radiusKm}${limitParam}`, options);
}

export function routeSafety(
  startLat: number,
  startLng: number,
  endLat: number,
  endLng: number,
  options: { includeComparison?: boolean; signal?: AbortSignal; at?: string } = {}
) {
  return request<RouteResult>("/safety/route", {
    method: "POST",
    body: JSON.stringify({
      start_lat: startLat,
      start_lng: startLng,
      end_lat: endLat,
      end_lng: endLng,
      include_comparison: options.includeComparison ?? true,
      at: options.at,
    }),
    signal: options.signal,
  });
}

export function listScoringProfiles() {
  return request<ScoringProfile[]>("/admin/scoring-profiles");
}

export function listScoreBuilds() {
  return request<ScoreBuild[]>("/admin/scoring-profiles/builds");
}

export function createScoringProfileDraft(draft: ScoringProfileDraft) {
  return request<ScoringProfile>("/admin/scoring-profiles", {
    method: "POST",
    body: JSON.stringify(draft),
  });
}

export function applyScoringProfile(profileId: number) {
  return request<ScoreBuild>(`/admin/scoring-profiles/${profileId}/apply`, { method: "POST" });
}
