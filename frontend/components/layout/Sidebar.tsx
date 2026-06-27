'use client';

import { useChatStore } from '@/stores/chatStore';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  MessageSquarePlus,
  Settings,
  Brain,
  Clock,
  Search,
} from 'lucide-react';
import { useState } from 'react';
import ContextUsageIndicator from '@/components/chat/ContextUsageIndicator';
import { useT, useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

export function Sidebar() {
  const { conversations, activeId, setActive, deleteConversation, newConversation, sidebarOpen, toggleSidebar, theme, toggleTheme } = useChatStore();
  const pathname = usePathname();
  const [search, setSearch] = useState('');
  const t = useT();
  const [locale] = useLocale();
  const brand = BRAND[locale];

  const filtered = search
    ? conversations.filter(
        (c) =>
          c.title.toLowerCase().includes(search.toLowerCase()) ||
          c.messages.some((m) => m.content.toLowerCase().includes(search.toLowerCase())),
      )
    : conversations;

  return (
    <aside
      className="flex flex-col border-r transition-all duration-200 overflow-hidden"
      style={{
        width: sidebarOpen ? '260px' : '0',
        minWidth: sidebarOpen ? '260px' : '0',
        background: 'var(--surface)',
        borderColor: 'var(--border)',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <img src={MASCOT_URL} alt={brand.name} className="w-7 h-7 rounded-full" />
        <div className="flex flex-col leading-tight min-w-0">
          <span className="font-semibold text-sm truncate">{brand.name}</span>
          <span className="text-[10px] truncate" style={{ color: 'var(--text-faint)' }}>{brand.slogan}</span>
        </div>
        <div className="ml-auto flex gap-1">
          <button
            onClick={toggleTheme}
            className="p-1.5 rounded-md transition-colors hover:bg-[var(--surface-3)]"
            title={t('sidebar.themeToggle')}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </div>
      </div>

      {/* New conversation */}
      <button
        onClick={newConversation}
        className="mx-2.5 mt-2.5 flex items-center gap-2 px-3 py-2 text-sm rounded-lg border transition-all hover:border-[var(--accent)]"
        style={{ borderColor: 'var(--border)' }}
      >
        <MessageSquarePlus size={15} className="opacity-60" />
        {t('sidebar.newChat')}
      </button>

      {/* Search */}
      <div className="relative mx-2.5 mt-2 mb-1.5">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 opacity-40" />
        <input
          type="text"
          placeholder={t('sidebar.searchPlaceholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg outline-none border"
          style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--text)' }}
        />
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-1.5">
        {[...filtered].reverse().map((c) => (
          <div
            key={c.id}
            onClick={() => {
              setActive(c.id);
              window.location.href = '/chat';
            }}
            className="group flex items-center px-2.5 py-2 rounded-lg cursor-pointer text-xs transition-colors"
            style={{
              background: c.id === activeId ? 'var(--surface-3)' : 'transparent',
              color: c.id === activeId ? 'var(--text)' : 'var(--text-2)',
            }}
          >
            <span className="flex-1 truncate">{c.title}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                deleteConversation(c.id);
              }}
              className="opacity-0 group-hover:opacity-50 hover:opacity-100 text-xs transition-opacity"
              style={{ color: 'var(--danger)' }}
            >
              ✕
            </button>
          </div>
        ))}
        {!filtered.length && (
          <div className="text-center text-xs py-4" style={{ color: 'var(--text-faint)' }}>
            {t('sidebar.emptyConversations')}
          </div>
        )}
      </div>

      {/* Footer: rage bar */}
      <div className="px-3 py-2 flex items-center gap-2" style={{ borderTop: '1px solid var(--border)' }}>
        <ContextUsageIndicator />
      </div>

      {/* Navigation links */}
      <div className="px-2.5 pb-2 flex flex-col gap-0.5">
        <NavLink href="/chat" icon={<MessageSquarePlus size={15} />} label={t('sidebar.nav.chat')} active={pathname === '/chat'} />
        <NavLink href="/memory" icon={<Brain size={15} />} label={t('sidebar.nav.memory')} active={pathname === '/memory'} />
        <NavLink href="/tasks" icon={<Clock size={15} />} label={t('sidebar.nav.tasks')} active={pathname === '/tasks'} />
        <NavLink href="/settings" icon={<Settings size={15} />} label={t('sidebar.nav.settings')} active={pathname === '/settings'} />
      </div>
    </aside>
  );
}

function NavLink({ href, icon, label, active }: { href: string; icon: React.ReactNode; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs transition-colors"
      style={{
        background: active ? 'var(--surface-3)' : 'transparent',
        color: active ? 'var(--text)' : 'var(--text-2)',
      }}
    >
      {icon}
      {label}
    </Link>
  );
}
