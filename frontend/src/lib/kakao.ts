export type LatLng = { lat: number; lng: number };

export type KakaoLatLng = {
  getLat(): number;
  getLng(): number;
};

export type KakaoLatLngBounds = {
  extend(position: KakaoLatLng): void;
};

export type KakaoMap = {
  relayout(): void;
  panTo(position: KakaoLatLng): void;
  setLevel(level: number): void;
  setBounds(bounds: KakaoLatLngBounds): void;
};

export type KakaoOverlay = {
  setMap(map: KakaoMap | null): void;
};

export type KakaoMouseEvent = {
  latLng: KakaoLatLng;
};

type KakaoAddressResult = {
  x: string;
  y: string;
  road_address?: { address_name?: string };
  address?: { address_name?: string };
};

export type KakaoSdk = {
  maps: {
    load(callback: () => void): void;
    Map: new (container: HTMLElement, options: { center: KakaoLatLng; level: number }) => KakaoMap;
    LatLng: new (lat: number, lng: number) => KakaoLatLng;
    LatLngBounds: new () => KakaoLatLngBounds;
    CustomOverlay: new (options: { position: KakaoLatLng; content: HTMLElement; yAnchor: number; zIndex: number }) => KakaoOverlay;
    InfoWindow: new (options: { position: KakaoLatLng; content: string; removable: boolean }) => { open(map: KakaoMap): void; close(): void };
    Polygon: new (options: { path: KakaoLatLng[][]; strokeWeight: number; strokeColor: string; strokeOpacity: number; fillColor: string; fillOpacity: number; zIndex: number }) => KakaoOverlay;
    Circle: new (options: { center: KakaoLatLng; radius: number; strokeWeight: number; strokeColor: string; strokeOpacity: number; fillColor: string; fillOpacity: number; zIndex: number }) => KakaoOverlay;
    Polyline: new (options: { path: KakaoLatLng[]; strokeWeight: number; strokeColor: string; strokeOpacity: number; strokeStyle: string }) => KakaoOverlay;
    event: {
      addListener(target: KakaoMap, event: "click" | "rightclick", handler: (event: KakaoMouseEvent) => void): void;
      addListener(target: KakaoOverlay, event: string, handler: () => void): void;
    };
    services: {
      Status: { OK: string };
      Geocoder: new () => {
        addressSearch(address: string, callback: (result: KakaoAddressResult[], status: string) => void): void;
        coord2Address(lng: number, lat: number, callback: (result: KakaoAddressResult[], status: string) => void): void;
      };
    };
  };
};

declare global {
  interface Window {
    kakao: KakaoSdk;
  }
}

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;
let sdkLoadPromise: Promise<void> | null = null;

export function loadKakaoSdk(): Promise<void> {
  if (window.kakao?.maps?.Map) return Promise.resolve();
  if (sdkLoadPromise) return sdkLoadPromise;

  sdkLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${KAKAO_KEY}&autoload=false&libraries=services`;
    script.onload = () => window.kakao.maps.load(() => resolve());
    script.onerror = (event) => {
      console.error("[kakao] SDK script load failed", event);
      sdkLoadPromise = null;
      reject(new Error("kakao sdk load failed"));
    };
    document.head.appendChild(script);
  });
  return sdkLoadPromise;
}

export async function geocodeAddress(address: string): Promise<LatLng | null> {
  await loadKakaoSdk();
  const { kakao } = window;
  return new Promise((resolve) => {
    const geocoder = new kakao.maps.services.Geocoder();
    geocoder.addressSearch(address, (result, status) => {
      if (status === kakao.maps.services.Status.OK && result[0]) {
        resolve({ lat: Number(result[0].y), lng: Number(result[0].x) });
      } else {
        resolve(null);
      }
    });
  });
}

export async function reverseGeocode(lat: number, lng: number): Promise<string | null> {
  await loadKakaoSdk();
  const { kakao } = window;
  return new Promise((resolve) => {
    const geocoder = new kakao.maps.services.Geocoder();
    geocoder.coord2Address(lng, lat, (result, status) => {
      if (status === kakao.maps.services.Status.OK && result[0]) {
        const address = result[0].road_address?.address_name ?? result[0].address?.address_name ?? null;
        resolve(address);
      } else {
        resolve(null);
      }
    });
  });
}
