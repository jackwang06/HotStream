import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HotStream · 前山如画，四季成歌",
  description: "文旅热点借势营销工具",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var t=localStorage.getItem('hotstream.theme');document.documentElement.setAttribute('data-theme',t==='light'?'light':'dark');}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();",
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
