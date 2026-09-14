"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { nearbyZones, residenceRecommend, routeSafety, type RouteResult, type SafetyZone } from "@/lib/api";
import { clearToken, getToken } from "@/lib/auth";
import { SafetyMap } from "@/components/SafetyMap";

// ponytail: 토큰을 localStorage에 보관 (XSS 노출 위험). 프로덕션 전환 시
// httpOnly 쿠키 기반 세션으로 교체하고 백엔드에 CSRF 보호 추가 필요.

export default function Dashboard() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [recommended, setRecommended] = useState<SafetyZone[]>([]);
  const [nearby, setNearby] = useState<SafetyZone[]>([]);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [myLocation, setMyLocation] = useState<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    residenceRecommend(5).then(setRecommended).catch((e) => setError(e.message));

    navigator.geolocation?.getCurrentPosition(
      (pos) => setMyLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => {} // 위치 거부/실패 시 기본 중심(서울시청) 유지
    );
  }, [router]);

  async function handleNearbySearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const lat = Number(form.get("lat"));
    const lng = Number(form.get("lng"));
    try {
      setNearby(await nearbyZones(lat, lng, 5));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "조회 실패");
    }
  }

  async function handleRouteSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      const result = await routeSafety(
        Number(form.get("startLat")),
        Number(form.get("startLng")),
        Number(form.get("endLat")),
        Number(form.get("endLng"))
      );
      setRoute(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "경로 조회 실패");
    }
  }

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  if (!ready) return null;

  const mapZones = Array.from(
    new Map(
      [...recommended, ...nearby, ...route?.zones_passed ?? []].map((z) => [z.dong_code, z])
    ).values()
  );

  return (
    <main style={{ maxWidth: 720, margin: "40px auto", padding: 16 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>안심 거주지 · 귀갓길 추천</h1>
        <button onClick={handleLogout}>로그아웃</button>
      </header>

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <section style={{ marginTop: 24 }}>
        <SafetyMap zones={mapZones} center={myLocation ?? undefined} />
      </section>

      <section style={{ marginTop: 32 }}>
        <h2>안심 거주지 추천 Top 5</h2>
        <ul>
          {recommended.map((z) => (
            <li key={z.dong_code}>
              {z.dong_name} — 안전지수 {z.safety_score.toFixed(1)}
            </li>
          ))}
        </ul>
      </section>

      <section style={{ marginTop: 32 }}>
        <h2>주변 안전 구역 검색</h2>
        <form onSubmit={handleNearbySearch} style={{ display: "flex", gap: 8 }}>
          <input name="lat" type="number" step="any" placeholder="위도" required />
          <input name="lng" type="number" step="any" placeholder="경도" required />
          <button type="submit">검색</button>
        </form>
        <ul>
          {nearby.map((z) => (
            <li key={z.dong_code}>
              {z.dong_name} — 안전지수 {z.safety_score.toFixed(1)}
            </li>
          ))}
        </ul>
      </section>

      <section style={{ marginTop: 32 }}>
        <h2>귀갓길 안전도 조회</h2>
        <form onSubmit={handleRouteSearch} style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 320 }}>
          <input name="startLat" type="number" step="any" placeholder="출발 위도" required />
          <input name="startLng" type="number" step="any" placeholder="출발 경도" required />
          <input name="endLat" type="number" step="any" placeholder="도착 위도" required />
          <input name="endLng" type="number" step="any" placeholder="도착 경도" required />
          <button type="submit">경로 안전도 확인</button>
        </form>
        {route && (
          <div style={{ marginTop: 12 }}>
            <p>경로 안전지수: {route.safety_score.toFixed(1)}</p>
            <ul>
              {route.zones_passed.map((z) => (
                <li key={z.dong_code}>
                  {z.dong_name} ({z.safety_score.toFixed(1)})
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </main>
  );
}
