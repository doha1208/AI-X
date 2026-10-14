import { beforeEach, describe, expect, it, vi } from "vitest";
import { placeFromQuery, placeQuery, searchAddressSuggestions } from "./place";

const searchKakaoAddresses = vi.fn();
const searchKakaoPlaces = vi.fn();
vi.mock("./kakao", () => ({
  searchKakaoAddresses: (...args: unknown[]) => searchKakaoAddresses(...args),
  searchKakaoPlaces: (...args: unknown[]) => searchKakaoPlaces(...args),
}));

beforeEach(() => {
  searchKakaoAddresses.mockReset().mockResolvedValue([]);
  searchKakaoPlaces.mockReset().mockResolvedValue([]);
});

describe("place query", () => {
  it("round-trips a place with a Korean label through the URL", () => {
    const place = { lat: 37.2901, lng: 127.0134, label: "망원동 458-1" };
    expect(placeFromQuery(`?${placeQuery("end", place)}`, "end")).toEqual(place);
  });

  it("rejects missing or out-of-range coordinates", () => {
    expect(placeFromQuery("", "end")).toBeNull();
    expect(placeFromQuery("?end=abc,127", "end")).toBeNull();
    expect(placeFromQuery("?end=95,127", "end")).toBeNull();
  });
});

it("keeps only addresses containing the entered tokens in order", async () => {
  searchKakaoAddresses.mockResolvedValue([
    { label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 },
    { label: "경기도 성남시 망포로 10", lat: 37.4, lng: 127.1 },
    { label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 },
  ]);
  expect(await searchAddressSuggestions("수원시 영통구 망포")).toEqual([
    { label: "경기도 수원시 영통구 망포동", lat: 37.24, lng: 127.06 },
    { label: "경기도 수원시 영통구 망포로 10", lat: 37.25, lng: 127.07 },
  ]);
});

it("does not request candidates for a one-character query", async () => {
  expect(await searchAddressSuggestions("수")).toEqual([]);
  expect(searchKakaoAddresses).not.toHaveBeenCalled();
});

it("checks a completed-syllable prefix when Kakao does not recognize mixed input", async () => {
  searchKakaoPlaces.mockImplementation((query: string, page: number) => Promise.resolve(
    query === "동" && page === 1 ? [
      { name: "동래역", label: "동래역 · 부산 동래구", lat: 35.2, lng: 129.1 },
      { name: "동수역", label: "동수역 · 인천 부평구", lat: 37.5, lng: 126.7 },
    ] : []
  ));

  expect(await searchAddressSuggestions("동ㄹ")).toEqual([
    { label: "동래역 · 부산 동래구", lat: 35.2, lng: 129.1 },
  ]);
});

it("matches consonant-only input only when Kakao supplies a matching place", async () => {
  searchKakaoPlaces.mockResolvedValue([
    { name: "상록수역", label: "상록수역 · 경기 안산시", lat: 37.3028, lng: 126.8668 },
  ]);
  expect(await searchAddressSuggestions("ㅅㄹㅅ")).toEqual([
    { label: "상록수역 · 경기 안산시", lat: 37.3028, lng: 126.8668 },
  ]);
});

it("does not fabricate a station when Kakao returns no matching candidate", async () => {
  expect(await searchAddressSuggestions("상ㄹ")).toEqual([]);
});

it("uses a station name only to fetch the same Kakao place for mixed and completed input", async () => {
  const kakaoPlace = { name: "상록수역 4호선", label: "상록수역 4호선 · 경기 안산시 본오동", lat: 37.3028, lng: 126.8668 };
  searchKakaoPlaces.mockImplementation((query: string, page: number, category?: string) => Promise.resolve(
    query === "상록수역" && category === "SW8" && page === 1 ? [kakaoPlace] : []
  ));

  const mixed = await searchAddressSuggestions("상ㄹ");
  const completed = await searchAddressSuggestions("상록");
  const expected = [{ label: kakaoPlace.label, lat: kakaoPlace.lat, lng: kakaoPlace.lng }];

  expect(mixed).toEqual(expected);
  expect(completed).toEqual(expected);
  expect(searchKakaoPlaces).toHaveBeenCalledWith("상록수역", 1, "SW8");
});

it("keeps a Kakao station visible when a completed query has five other matches", async () => {
  const station = { name: "상록수역 4호선", label: "상록수역 4호선 · 경기 안산시", lat: 37.3028, lng: 126.8668 };
  const otherPlaces = Array.from({ length: 5 }, (_, index) => ({
    name: `상록 상점 ${index}`, label: `상록 상점 ${index} · 경기`, lat: 37.3 + index / 100, lng: 126.8,
  }));
  searchKakaoPlaces.mockImplementation((query: string, _page: number, category?: string) => Promise.resolve(
    query === "상록수역" && category === "SW8" ? [station] : query === "상록" ? otherPlaces : []
  ));

  const suggestions = await searchAddressSuggestions("상록");

  expect(suggestions).toHaveLength(5);
  expect(suggestions[0]).toEqual({ label: station.label, lat: station.lat, lng: station.lng });
});
