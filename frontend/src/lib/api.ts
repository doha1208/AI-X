const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type SafetyZone = {
  dong_code: string;
  dong_name: string;
  lat: number;
  lng: number;
  safety_score: number;
};

export type RouteResult = {
  safety_score: number;
  zones_passed: SafetyZone[];
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed: ${res.status}`);
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

export function routeSafety(
  startLat: number,
  startLng: number,
  endLat: number,
  endLng: number
) {
  return request<RouteResult>("/safety/route", {
    method: "POST",
    body: JSON.stringify({
      start_lat: startLat,
      start_lng: startLng,
      end_lat: endLat,
      end_lng: endLng,
    }),
  });
}
