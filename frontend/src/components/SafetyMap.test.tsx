import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { KakaoSdk } from "@/lib/kakao";

const state = vi.hoisted(() => {
  process.env.NEXT_PUBLIC_KAKAO_MAP_KEY = "test-key";
  return {
    map: { relayout: vi.fn(), panTo: vi.fn(), getLevel: vi.fn(() => 6), setLevel: vi.fn(), setBounds: vi.fn(), getProjection: vi.fn() },
    resizeCallback: null as ResizeObserverCallback | null,
    loadKakaoSdk: vi.fn(() => Promise.resolve()),
  };
});

vi.mock("@/lib/kakao", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/kakao")>()),
  loadKakaoSdk: state.loadKakaoSdk,
}));

import { SafetyMap } from "./SafetyMap";

function installKakao() {
  function LatLng(lat: number, lng: number) {
    return { getLat: () => lat, getLng: () => lng };
  }
  window.kakao = {
    maps: {
      load: (callback: () => void) => callback(),
      Map: function Map() { return state.map; },
      LatLng,
      LatLngBounds: function LatLngBounds() { return { extend: vi.fn() }; },
      Point: function Point(x: number, y: number) { return { x, y }; },
      CustomOverlay: function CustomOverlay() { return { setMap: vi.fn() }; },
      InfoWindow: function InfoWindow() { return { open: vi.fn(), close: vi.fn() }; },
      Polygon: function Polygon() { return { setMap: vi.fn() }; },
      Circle: function Circle() { return { setMap: vi.fn() }; },
      Polyline: function Polyline() { return { setMap: vi.fn() }; },
      event: { addListener: vi.fn() },
      services: { Status: { OK: "OK" }, Geocoder: function Geocoder() { return {}; } },
    },
  } as unknown as KakaoSdk;
}

describe("SafetyMap container resize", () => {
  beforeEach(() => {
    state.loadKakaoSdk.mockClear();
    state.map.relayout.mockClear();
    state.resizeCallback = null;
    installKakao();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: ResizeObserverCallback) { state.resizeCallback = callback; }
      observe() {}
      disconnect() {}
      unobserve() {}
    });
  });

  it("relayouts Kakao tiles when the map container height changes", async () => {
    render(<SafetyMap height="100%" />);

    await waitFor(() => expect(state.loadKakaoSdk).toHaveBeenCalled());
    await waitFor(() => expect(state.resizeCallback).not.toBeNull());

    state.resizeCallback?.([], {} as ResizeObserver);

    expect(state.map.relayout).toHaveBeenCalledTimes(1);
  });
});
