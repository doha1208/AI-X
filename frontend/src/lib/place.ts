import { geocodeAddress, searchKakaoAddresses, searchKakaoPlaces, type LatLng } from "./kakao";
import stationIndex from "../../public/data/gyeonggi-stations.json";

export type Place = LatLng & { label: string };

const INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";

function matchesToken(text: string, token: string, from: number): number {
  for (let start = from; start <= text.length - token.length; start++) {
    let matched = true;
    for (let offset = 0; offset < token.length; offset++) {
      const wanted = token[offset];
      const actual = text[start + offset];
      const syllable = actual.charCodeAt(0) - 0xac00;
      if (actual !== wanted && !(INITIALS.includes(wanted) && syllable >= 0 && syllable < 11172 && INITIALS[Math.floor(syllable / 588)] === wanted)) {
        matched = false;
        break;
      }
    }
    if (matched) return start + token.length;
  }
  return -1;
}

function matchesQuery(text: string, query: string): boolean {
  let from = 0;
  const candidate = text.toLocaleLowerCase();
  for (const token of query.toLocaleLowerCase().split(" ")) {
    from = matchesToken(candidate, token, from);
    if (from < 0) return false;
  }
  return true;
}

// 입력한 완성형 음절은 그대로, 단독 자음은 해당 위치의 초성으로만 비교한다.
export async function searchAddressSuggestions(text: string): Promise<Place[]> {
  const query = text.trim().replace(/\s+/g, " ");
  if (query.length < 2 || /^[-\d.,\s]+$/.test(query)) return [];
  const hasInitial = [...query].some((char) => INITIALS.includes(char));
  const stations = hasInitial ? stationIndex.stations
    .filter((station) => matchesQuery(station.name, query))
    .map((station) => ({
      label: station.name.endsWith("역") ? station.name : `${station.name}역`,
      lat: station.lat,
      lng: station.lng,
    })) : [];
  if (stations.length) return stations.slice(0, 5);
  const collect = (results: PromiseSettledResult<Place[]>[], placeResults: PromiseSettledResult<(Place & { name: string })[]>[]): Place[] => {
    const addresses = results.flatMap((result) => result.status === "fulfilled" ? result.value : []);
    const places = placeResults.flatMap((result) => result.status === "fulfilled" ? result.value : []);
    const seen = new Set<string>();
    return [
      ...addresses.filter((place) => matchesQuery(place.label, query)),
      ...places.filter((place) => matchesQuery(place.name, query)),
    ].filter((place) => {
      const key = `${place.label}|${place.lat}|${place.lng}`;
      if (!place.label || !Number.isFinite(place.lat) || !Number.isFinite(place.lng) || seen.has(key)) return false;
      seen.add(key);
      return true;
    }).map(({ label, lat, lng }) => ({ label, lat, lng })).slice(0, 5);
  };

  const [addresses, places] = await Promise.all([
    Promise.allSettled([searchKakaoAddresses(query)]),
    Promise.allSettled([searchKakaoPlaces(query, 1)]),
  ]);
  const direct = collect(addresses, places);
  const firstConsonant = [...query].findIndex((char) => INITIALS.includes(char));
  if (direct.length || firstConsonant < 1) return direct;

  // 카카오가 혼합 입력을 직접 찾지 못한 경우, 완성형 접두어 검색 결과도 검사한다.
  const prefix = query.slice(0, firstConsonant).trim();
  if (!prefix) return direct;
  const [prefixAddresses, prefixPlaces] = await Promise.all([
    Promise.allSettled([searchKakaoAddresses(prefix)]),
    Promise.allSettled([1, 2, 3].map((page) => searchKakaoPlaces(prefix, page))),
  ]);
  return collect(prefixAddresses, prefixPlaces);
}

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
