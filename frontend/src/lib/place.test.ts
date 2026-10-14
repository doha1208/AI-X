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

it("matches consonant-only input against the local station index", async () => {
  expect(await searchAddressSuggestions("ㅅㄹㅅ")).toContainEqual({
    label: "상록수역", lat: 37.302813, lng: 126.866778,
  });
});

it("offers the bundled 상록수 station for 상ㄹ even when Kakao returns nothing", async () => {
  expect(await searchAddressSuggestions("상ㄹ")).toContainEqual({
    label: "상록수역", lat: 37.302813, lng: 126.866778,
  });
});
