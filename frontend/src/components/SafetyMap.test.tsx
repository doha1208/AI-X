import { render, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { KakaoSdk } from "@/lib/kakao";
import type { FacilityZone } from "@/lib/api";

const state = vi.hoisted(() => {
  process.env.NEXT_PUBLIC_KAKAO_MAP_KEY = "test-key";
  return {
    map: { relayout: vi.fn(), panTo: vi.fn(), getLevel: vi.fn(() => 6), setLevel: vi.fn(), setBounds: vi.fn(), getProjection: vi.fn() },
    resizeCallback: null as ResizeObserverCallback | null,
    loadKakaoSdk: vi.fn(() => Promise.resolve()),
    infoContent: [] as string[],
    overlayTitles: [] as string[],
  };
});

vi.mock("@/lib/kakao", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/kakao")>()),
  loadKakaoSdk: state.loadKakaoSdk,
}));

import { SafetyMap, type SafetyMapHandle } from "./SafetyMap";

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
      CustomOverlay: function CustomOverlay({ content }: { content: HTMLElement }) {
        state.overlayTitles.push(content.title);
        return { setMap: vi.fn() };
      },
      InfoWindow: function InfoWindow({ content }: { content: string }) {
        state.infoContent.push(content);
        return { open: vi.fn(), close: vi.fn() };
      },
      Polygon: function Polygon() { return { setMap: vi.fn() }; },
      Circle: function Circle() { return { setMap: vi.fn() }; },
      Polyline: function Polyline() { return { setMap: vi.fn() }; },
      event: { addListener: vi.fn() },
      services: { Status: { OK: "OK" }, Geocoder: function Geocoder() { return {}; } },
    },
  } as unknown as KakaoSdk;
}

describe("SafetyMap", () => {
  beforeEach(() => {
    state.loadKakaoSdk.mockClear();
    state.map.relayout.mockClear();
    state.map.setBounds.mockClear();
    state.map.panTo.mockClear();
    state.resizeCallback = null;
    state.infoContent.length = 0;
    state.overlayTitles.length = 0;
    installKakao();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: ResizeObserverCallback) { state.resizeCallback = callback; }
      observe() {}
      disconnect() {}
      unobserve() {}
    });
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
  });

  it("relayouts Kakao tiles when the map container height changes", async () => {
    render(<SafetyMap height="100%" />);

    await waitFor(() => expect(state.loadKakaoSdk).toHaveBeenCalled());
    await waitFor(() => expect(state.resizeCallback).not.toBeNull());

    state.resizeCallback?.([], {} as ResizeObserver);

    expect(state.map.relayout).toHaveBeenCalledTimes(1);
  });

  it("fits the active route again after the map container changes size", async () => {
    render(<SafetyMap height="100%" routePath={[{ lat: 37.532, lng: 126.99 }, { lat: 37.548, lng: 127.01 }]} />);

    await waitFor(() => expect(state.map.setBounds).toHaveBeenCalledTimes(1));
    state.resizeCallback?.([], {} as ResizeObserver);

    await waitFor(() => expect(state.map.setBounds).toHaveBeenCalledTimes(2));
  });

  it("uses the workspace panel inset when fitting a desktop route", async () => {
    const { container } = render(<SafetyMap height="100%" routePath={[{ lat: 37.3, lng: 127.04 }, { lat: 37.31, lng: 127.05 }]} />);
    (container.firstElementChild as HTMLElement).style.setProperty("--map-panel-inset", "412px");
    await waitFor(() => expect(state.map.setBounds).toHaveBeenCalledWith(expect.anything(), 16, 16, 16, 412));
  });

  it("places a searched location in the visible map area beside the panel", async () => {
    const ref = createRef<SafetyMapHandle>();
    state.map.getProjection.mockReturnValue({
      pointFromCoords: () => ({ x: 500, y: 300 }),
      coordsFromPoint: (point: { x: number; y: number }) => point,
    });
    const { container } = render(<SafetyMap ref={ref} height="100%" />);
    (container.firstElementChild as HTMLElement).style.setProperty("--map-panel-inset", "412px");
    await waitFor(() => expect(state.resizeCallback).not.toBeNull());
    ref.current?.panTo({ lat: 37.3, lng: 127.04 });
    expect(state.map.panTo).toHaveBeenCalledWith({ x: 302, y: 300 });
  });

  it("shows only the name and the facility band on polygon and pin hover", async () => {
    const zone: FacilityZone = {
      dong_code: "A", dong_name: "가동", lat: 37.5, lng: 127,
      rank: 1, rank_tied: true, relative_percentile: 83, result_group_id: "result",
      assessment: {
        status: "degraded", evaluation_basis: "multi_factor", score: 42, reference_score: null,
        reference_factor: null, score_bounds: null, sampled_length_m: 100, used_factors: ["bell", "cctv"],
        factor_coverage: {}, factor_evaluation_ratio: {}, verified_distance_ratio: 1, basis_id: "basis",
        artifact_version: "v1", model_version: null, policy_version: null, schedule_key: "day",
        assessed_at: null, reference_at: null, unavailable_reason: null,
      },
    };
    render(<SafetyMap displayMetric="facility_access" zones={[zone]} rankedZones={[zone]} facilityGroup={{
      basis_id: "basis", result_group_id: "result", relative_status: "available", zone_count: 100, used_factors: ["bell", "cctv"],
    }} />);
    await waitFor(() => expect(state.infoContent).toContainEqual(expect.stringContaining(">가동 (상위권)</div>")));
    expect(state.overlayTitles).toContain("가동 상위권");
  });
});
