export type MapInsets = { top: number; right: number; bottom: number; left: number };

// 모바일에서 지도를 덮는 카드(상단 검색·경로 요약·방향 안내 카드)가 차지하는 높이(px).
const MOBILE_TOP_OVERLAY_PX = 96;
// 하단 시트 위쪽에 남기는 여유 — 경로선과 시트 사이가 딱 붙어 보이지 않게 한다.
const SHEET_GAP_PX = 16;
// 시트 높이를 모를 때도 접힌 시트(104px)만큼은 비운다.
const COLLAPSED_SHEET_PX = 104;

const NO_INSETS: MapInsets = { top: 0, right: 0, bottom: 0, left: 0 };

// 지도에서 실제로 눈에 보이는 영역 기준으로 경로를 맞추기 위한 여백. 데스크톱은 패널이 지도 옆에
// 있어 지도를 덮지 않으므로 여백이 없다.
export function visibleMapInsets(isMobile: boolean, sheetHeightPx: number): MapInsets {
  if (!isMobile) return NO_INSETS;
  const sheet = sheetHeightPx > 0 ? sheetHeightPx : COLLAPSED_SHEET_PX;
  return { top: MOBILE_TOP_OVERLAY_PX, right: 0, bottom: Math.round(sheet) + SHEET_GAP_PX, left: 0 };
}

// "312px" → 312. CSS 변수 값을 읽을 때 쓴다(변수가 없거나 px가 아니면 0).
export function parsePx(value: string): number {
  const match = /^(\d+(?:\.\d+)?)px$/.exec(value.trim());
  return match ? Number(match[1]) : 0;
}
