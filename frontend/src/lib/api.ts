// 배포 기본값은 동일 출처 프록시다. 로컬에서는 .env.local로 localhost:8000을 지정한다.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;
let refreshRequest: Promise<boolean> | null = null;

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
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
};

export type RouteMode = "safety_weighted" | "tmap" | "straight_line";

export type RouteResult = {
  safety_score: number;
  zones_passed: SafetyZone[];
  route_points: { lat: number; lng: number }[];
  mode: RouteMode;
  alternatives: RouteAlternative[];
  shortest_route_points: { lat: number; lng: number }[] | null;
};

export type RouteAlternative = {
  route_points: { lat: number; lng: number }[];
  safety_score: number;
  distance_m: number;
  zones_passed: SafetyZone[];
};

export type User = { id: number; email: string };

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
  if (res.status === 401 && !retried && !path.startsWith("/auth/")) {
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
  options: { includeComparison?: boolean; signal?: AbortSignal } = {}
) {
  return request<RouteResult>("/safety/route", {
    method: "POST",
    body: JSON.stringify({
      start_lat: startLat,
      start_lng: startLng,
      end_lat: endLat,
      end_lng: endLng,
      include_comparison: options.includeComparison ?? true,
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
