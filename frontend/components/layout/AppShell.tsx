'use client';

import { useEffect } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { Sidebar } from './Sidebar';
import { Menu, X } from 'lucide-react';
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
    <div className="flex h-screen w-screen overflow-hidden" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 relative">
        {/* Top bar */}
        <header
          className="flex items-center gap-3 px-4 h-12 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          {!sidebarOpen && (
            <button
              onClick={toggleSidebar}
              className="p-1.5 rounded-md hover:bg-[var(--surface-2)]"
            >
              <Menu size={18} style={{ color: 'var(--text-2)' }} />
            </button>
          )}
          {sidebarOpen && (
            <button
              onClick={toggleSidebar}
              className="p-1.5 rounded-md hover:bg-[var(--surface-2)]"
            >
              <X size={18} style={{ color: 'var(--text-2)' }} />
            </button>
          )}
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-2)' }}>
            <img
              src="http://127.0.0.1:8765/static/mascot.png"
              alt={brand.name}
              className="w-5 h-5 rounded-full"
            />
            <span className="font-medium">{brand.name}</span>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-hidden">{children}</div>
      </main>
    </div>
  );
}
