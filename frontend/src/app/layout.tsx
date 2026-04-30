import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniOps — 智能诊断与建议系统",
  description: "结构化数据驱动的 Multi-Agent 运维诊断平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="grain-overlay antialiased">
        {children}
      </body>
    </html>
  );
}
