// 배포 기본값은 동일 출처 프록시다. 로컬에서는 .env.local로 localhost:8000을 지정한다.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

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
  shortest_route_points: { lat: number; lng: number }[] | null;
};

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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(errorMessage(body.detail, `Request failed: ${res.status}`));
  }
  return res.json();
}

export function signup(email: string, password: string) {
  return request("/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function login(email: string, password: string) {
  return request<{ access_token: string; refresh_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function me(token: string) {
  return request("/auth/me", { headers: { Authorization: `Bearer ${token}` } });
}

export function residenceRecommend(limit = 5) {
  return request<SafetyZone[]>(`/safety/residence-recommend?limit=${limit}`);
}

export function nearbyZones(lat: number, lng: number, radiusKm = 2) {
  return request<SafetyZone[]>(
    `/safety/zones?lat=${lat}&lng=${lng}&radius_km=${radiusKm}`
  );
}

export function nearbyBells(lat: number, lng: number, radiusKm = 1, limit?: number) {
  const limitParam = limit ? `&limit=${limit}` : "";
  return request<{ lat: number; lng: number }[]>(
    `/safety/bells?lat=${lat}&lng=${lng}&radius_km=${radiusKm}${limitParam}`
  );
}

export function routeSafety(
  startLat: number,
  startLng: number,
  endLat: number,
  endLng: number,
  options: { includeComparison?: boolean } = {}
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
  });
}

function adminRequest<T>(path: string, token: string, options: RequestInit = {}) {
  return request<T>(path, { ...options, headers: { Authorization: `Bearer ${token}`, ...options.headers } });
}

export function listScoringProfiles(token: string) {
  return adminRequest<ScoringProfile[]>("/admin/scoring-profiles", token);
}

export function listScoreBuilds(token: string) {
  return adminRequest<ScoreBuild[]>("/admin/scoring-profiles/builds", token);
}

export function createScoringProfileDraft(token: string, draft: ScoringProfileDraft) {
  return adminRequest<ScoringProfile>("/admin/scoring-profiles", token, {
    method: "POST",
    body: JSON.stringify(draft),
  });
}

export function applyScoringProfile(token: string, profileId: number) {
  return adminRequest<ScoreBuild>(`/admin/scoring-profiles/${profileId}/apply`, token, { method: "POST" });
}
