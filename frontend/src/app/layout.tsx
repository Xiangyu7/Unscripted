import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Unscripted | 非剧本杀",
  description:
    "多智能体互动叙事游戏 - Multi-agent interactive narrative game",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="bg-slate-950 text-slate-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
