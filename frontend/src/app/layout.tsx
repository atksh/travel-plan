import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Generalized Travel Planner",
  description: "候補収集、計画、比較、実行までをつなぐ単日旅行プランナー",
};

export const viewport: Viewport = {
  themeColor: "#0d1520",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
