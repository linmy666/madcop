import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'MadCop Agent · Infinite Minds, Boundless Strides',
  description: 'A local-first AI agent with 4-layer growing memory, tool-use, and streaming web UI.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>{children}</body>
    </html>
  );
}
