import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'madcop',
  description: '本地 AI Agent — 记忆、搜索、天气、文件操作',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" data-theme="dark">
      <body>{children}</body>
    </html>
  );
}
