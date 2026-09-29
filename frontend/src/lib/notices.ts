import type { Notice } from "./notifications";

// 서버 없이 앱과 함께 배포되는 공지 — 새 공지는 id를 새로 지어 맨 위에 추가하면 처음 여는 사용자에게 한 번 알림으로 뜬다.
// ponytail: 코드에 박힌 정적 목록 — 재배포 없이 공지를 바꿔야 하면 서버 엔드포인트로 옮긴다.
export const NOTICES: readonly Notice[] = [
  {
    id: "2026-09-guidance-tools",
    at: Date.parse("2026-09-29T00:00:00+09:00"),
    text: "길안내에서 보호자 문자, 화면 꺼짐 방지, 위치 오차 표시를 쓸 수 있어요. 내 정보에서 긴급 연락처를 먼저 등록해보세요.",
  },
];
