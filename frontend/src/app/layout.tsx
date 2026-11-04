import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

// 한글 UI 글꼴. 쓰는 글자만 나눠 받는(dynamic subset) CSS라 첫 화면이 무겁지 않다. 버전은 고정한다.
const PRETENDARD_CSS =
  "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css";

export const metadata: Metadata = {
  title: "안심 거주지 · 귀갓길 추천",
  description: "공개 데이터 기반 거주지·귀갓길 참고 정보 서비스",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  interactiveWidget: "resizes-content",
  themeColor: "#1f3a5f",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://cdn.jsdelivr.net" crossOrigin="anonymous" />
        <link rel="stylesheet" href={PRETENDARD_CSS} crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
