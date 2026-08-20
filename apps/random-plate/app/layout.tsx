import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Random Plate — 오늘 점심 뭐 먹지?",
  description:
    "링크 하나로 팀이 같이 점심 메뉴를 정하는 웹앱. 로그인 없음, 설치 없음.",
  openGraph: {
    title: "Random Plate — 오늘 점심 뭐 먹지?",
    description: "룰렛 한 번이면 끝. 로그인도 설치도 필요 없습니다.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#0b0b12",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
