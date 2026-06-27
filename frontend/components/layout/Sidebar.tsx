'use client';

import { useChatStore } from '@/stores/chatStore';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Plus,
  Settings,
  Brain,
  Clock,
  BookOpen,
  Search,
  X,
} from 'lucide-react';
import { useState } from 'react';
import ContextUsageIndicator from '@/components/chat/ContextUsageIndicator';
import { useT, useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

export function Sidebar() {
  const conversations = useChatStore((s) => s.conversations);
  const activeId = useChatStore((s) => s.activeId);
  const setActive = useChatStore((s) => s.setActive);
  const deleteConversation = useChatStore((s) => s.deleteConversation);
  const newConversation = useChatStore((s) => s.newConversation);
  const theme = useChatStore((s) => s.theme);
  const toggleTheme = useChatStore((s) => s.toggleTheme);
  const sidebarOpen = useChatStore((s) => s.sidebarOpen);
  const toggleSidebar = useChatStore((s) => s.toggleSidebar);
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

  if (!sidebarOpen) {
    return null;
  }

  return (
    <aside
      className="flex flex-col border-r overflow-hidden flex-shrink-0"
      style={{
        width: '240px',
        background: 'var(--surface)',
        borderColor: 'var(--border)',
      }}
    >
      {/* Brand header */}
      <div
        className="flex items-center gap-2 px-3 h-12"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <img
          src={MASCOT_URL}
          alt={brand.name}
          className="w-7 h-7 rounded-full object-cover"
          style={{ boxShadow: 'var(--shadow-sm)' }}
        />
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold leading-tight truncate">
            {brand.name}
          </div>
          <div
            className="text-[10px] italic leading-tight truncate"
            style={{ color: 'var(--text-faint)' }}
          >
            {brand.slogan}
          </div>
        </div>
        <button
          onClick={toggleTheme}
          className="flex h-7 w-7 items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-2)' }}
          title={t('sidebar.themeToggle')}
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
        <button
          onClick={toggleSidebar}
          className="flex h-7 w-7 items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-2)' }}
          title="Toggle sidebar"
        >
          <X size={14} />
        </button>
      </div>

      {/* New conversation */}
      <div className="px-2 pt-2">
        <button
          onClick={newConversation}
          className="flex items-center gap-2 w-full px-3 py-1.5 text-[13px] rounded-md border transition-colors"
          style={{
            background: 'var(--surface-1)',
            borderColor: 'var(--border)',
            color: 'var(--text)',
          }}
        >
          <Plus size={14} className="opacity-70" />
          {t('sidebar.newChat')}
        </button>
      </div>

      {/* Search */}
      <div className="px-2 mt-1.5">
        <div className="relative">
          <Search
            size={12}
            className="absolute left-2.5 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--text-faint)' }}
          />
          <input
            type="text"
            placeholder={t('sidebar.searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-7 pr-2 py-1.5 text-[12px] rounded-md border outline-none"
            style={{
              background: 'var(--surface-1)',
              borderColor: 'var(--border)',
              color: 'var(--text)',
            }}
          />
        </div>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto py-1.5 px-1.5">
        {[...filtered].reverse().map((c) => (
          <div
            key={c.id}
            onClick={() => {
              setActive(c.id);
              window.location.href = '/chat';
            }}
            className="group flex items-center px-2 py-1.5 rounded-md cursor-pointer text-[12px] transition-colors"
            style={{
              background: c.id === activeId ? 'var(--surface-active)' : 'transparent',
              color: c.id === activeId ? 'var(--text)' : 'var(--text-2)',
            }}
          >
            <span className="flex-1 truncate">{c.title}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                deleteConversation(c.id);
              }}
              className="opacity-0 group-hover:opacity-60 hover:opacity-100 text-[11px] ml-1"
              style={{ color: 'var(--danger)' }}
            >
              <X size={11} />
            </button>
          </div>
        ))}
        {!filtered.length && (
          <div className="text-center text-[11px] py-4" style={{ color: 'var(--text-faint)' }}>
            {t('sidebar.emptyConversations')}
          </div>
        )}
      </div>

      {/* Rage bar */}
      <div
        className="px-3 py-2 flex items-center gap-2"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <ContextUsageIndicator />
      </div>

      {/* Navigation */}
      <div
        className="px-1.5 pb-2 flex flex-col gap-0.5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <NavLink href="/chat" icon={<Plus size={14} />} label={t('sidebar.nav.chat')} active={pathname === '/chat'} />
        <NavLink href="/memory" icon={<Brain size={14} />} label={t('sidebar.nav.memory')} active={pathname === '/memory'} />
        <NavLink href="/tasks" icon={<Clock size={14} />} label={t('sidebar.nav.tasks')} active={pathname === '/tasks'} />
        <NavLink href="/skills" icon={<BookOpen size={14} />} label={t('sidebar.nav.skills')} active={pathname === '/skills'} />
        <NavLink href="/settings" icon={<Settings size={14} />} label={t('sidebar.nav.settings')} active={pathname === '/settings'} />
      </div>
    </aside>
  );
}

function NavLink({ href, icon, label, active }: { href: string; icon: React.ReactNode; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[12px] transition-colors"
      style={{
        background: active ? 'var(--surface-active)' : 'transparent',
        color: active ? 'var(--text)' : 'var(--text-2)',
      }}
    >
      {icon}
      {label}
    </Link>
  );
}
