import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 개발 서버는 기본적으로 localhost 외 출처의 요청을 막는다(CSRF 방지) — cloudflared
  // 등으로 외부에 테스트 공유할 때는 그 터널 도메인을 여기 추가해야 페이지가 뜬다.
  // ponytail: 매번 랜덤 서브도메인이라 와일드카드로 전체 허용 — 공유 기간에만 켜둘 것.
  allowedDevOrigins: ["ansimnavi.duckdns.org"],
  // 개발 서버가 왼쪽 아래에 붙이는 "N" 표시가 모바일 하단 탭(안심 거주지)을 가린다. 컴파일·런타임 오류는 계속 표시된다.
  devIndicators: false,
};

export default nextConfig;
