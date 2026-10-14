import { afterEach, expect, it, vi } from "vitest";
import { geocodeAddress, searchKakaoPlaces, type KakaoSdk } from "./kakao";

afterEach(() => { delete (window as Partial<Window>).kakao; });

it("requires an exact address when resolving a submitted text query", async () => {
  const addressSearch = vi.fn((_query, callback: (results: { x: string; y: string }[], status: string) => void) => {
    callback([{ x: "127.06", y: "37.24" }], "OK");
  });
  window.kakao = { maps: { Map: class {}, services: { Status: { OK: "OK" }, Geocoder: class { addressSearch = addressSearch; } } } } as unknown as KakaoSdk;
  expect(await geocodeAddress("경기도 수원시 영통구 망포동")).toEqual({ lat: 37.24, lng: 127.06 });
  expect(addressSearch).toHaveBeenCalledWith("경기도 수원시 영통구 망포동", expect.any(Function), { analyze_type: "EXACT" });
});

it("returns named Kakao places with coordinates and a distinguishing address", async () => {
  const keywordSearch = vi.fn((_query, callback: (results: { place_name: string; address_name: string; x: string; y: string }[], status: string) => void) => {
    callback([{ place_name: "상록수역", address_name: "경기 안산시 상록구", x: "126.846", y: "37.302" }], "OK");
  });
  window.kakao = { maps: { Map: class {}, services: { Status: { OK: "OK" }, Places: class { keywordSearch = keywordSearch; } } } } as unknown as KakaoSdk;

  expect(await searchKakaoPlaces("상ㄹ", 1)).toEqual([
    { name: "상록수역", label: "상록수역 · 경기 안산시 상록구", lat: 37.302, lng: 126.846 },
  ]);
});
