import { geocodeAddress, type LatLng } from "./kakao";

export type Place = LatLng & { label: string };

function validLatLng(lat: number, lng: number): boolean {
  return Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180;
}

// 탭 사이로 장소를 넘길 때 쓰는 쿼리: ?end=37.1,127.2&endName=...
export function placeQuery(key: string, place: Place): string {
  return `${key}=${place.lat.toFixed(6)},${place.lng.toFixed(6)}&${key}Name=${encodeURIComponent(place.label)}`;
}

export function placeFromQuery(search: string, key: string): Place | null {
  const params = new URLSearchParams(search);
  const [lat, lng] = (params.get(key) ?? "").split(",").map(Number);
  if (!validLatLng(lat, lng)) return null;
  return { lat, lng, label: params.get(`${key}Name`) || `${lat.toFixed(5)}, ${lng.toFixed(5)}` };
}

// 주소 검색. "37.55, 126.92"처럼 좌표를 직접 넣어도 된다(지오코딩 실패 대비).
export async function resolvePlace(text: string): Promise<Place | null> {
  const label = text.trim();
  if (!label) return null;
  const [lat, lng] = label.split(",").map((v) => Number(v.trim()));
  if (label.includes(",") && validLatLng(lat, lng)) return { lat, lng, label };
  const coords = await geocodeAddress(label);
  return coords ? { ...coords, label } : null;
}
