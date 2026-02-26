import type { Metadata } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";

import Nav from "@/components/layout/Nav";
import "./globals.css";

const heading = Space_Grotesk({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-heading"
});

const mono = IBM_Plex_Mono({
  weight: ["400", "500"],
  subsets: ["latin"],
  variable: "--font-mono"
});

export const metadata: Metadata = {
  title: "BTC Observer Dashboard",
  description: "Bitcoin 资金流与阶段判定看板"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className={`${heading.variable} ${mono.variable}`}>
        <div className="bgAura" />
        <Nav />
        <main className="container">{children}</main>
        <footer className="footer">本看板仅供信息参考，不构成任何投资建议。</footer>
      </body>
    </html>
  );
}
