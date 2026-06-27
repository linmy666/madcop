'use client';

import { useEffect } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { Sidebar } from './Sidebar';
import { PanelLeft } from 'lucide-react';
import { useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { theme, sidebarOpen, toggleSidebar } = useChatStore();
  const [locale] = useLocale();
  const brand = BRAND[locale];

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  return (
    <div
      className="flex h-screen w-screen overflow-hidden"
      style={{ background: 'var(--bg)' }}
    >
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 relative">
        {/* Top bar */}
        <header
          className="flex items-center gap-2 px-3 h-9 flex-shrink-0"
          style={{
            background: 'var(--surface)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          {!sidebarOpen && (
            <button
              onClick={toggleSidebar}
              className="h-7 w-7 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
              style={{ color: 'var(--text-2)' }}
              title="Open sidebar"
            >
              <PanelLeft size={15} />
            </button>
          )}
          <div className="flex items-center gap-2 text-[12px]" style={{ color: 'var(--text-2)' }}>
            <img
              src="http://127.0.0.1:8765/static/mascot.png"
              alt={brand.name}
              className="w-5 h-5 rounded-full object-cover"
            />
            <span className="font-medium">{brand.name}</span>
            <span
              className="text-[10px] italic"
              style={{ color: 'var(--text-faint)' }}
            >
              {brand.slogan}
            </span>
          </div>
        </header>

        <div className="flex-1 overflow-hidden">{children}</div>
      </main>
    </div>
  );
}
