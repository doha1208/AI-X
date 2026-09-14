declare global {
  interface Window {
    kakao: any;
  }
}

export type LatLng = { lat: number; lng: number };

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
    geocoder.addressSearch(address, (result: any[], status: string) => {
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
    geocoder.coord2Address(lng, lat, (result: any[], status: string) => {
      if (status === kakao.maps.services.Status.OK && result[0]) {
        const address = result[0].road_address?.address_name ?? result[0].address?.address_name ?? null;
        resolve(address);
      } else {
        resolve(null);
      }
    });
  });
}
