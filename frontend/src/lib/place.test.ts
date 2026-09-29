import { describe, expect, it } from "vitest";
import { placeFromQuery, placeQuery } from "./place";

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
