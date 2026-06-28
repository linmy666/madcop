'use client';

import { useChatStore } from '@/stores/chatStore';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import ContextUsageIndicator from '@/components/chat/ContextUsageIndicator';
import { useT, useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';
import {
  Settings,
  Send,
  Clock,
  History,
  Plus,
  Search,
  X,
  Trash2,
} from 'lucide-react';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

/**
 * MadCop Agent — Sidebar
 * Pattern adapted from production agent UIs (compact vertical icon rail
 * with collapsible expanded view). Pure CSS — no external design libs.
 */
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
  const [expanded, setExpanded] = useState(true); // session list expanded
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
        width: '260px',
        background: 'var(--surface)',
        borderColor: 'var(--border)',
      }}
    >
      {/* Brand header */}
      <div
        className="flex items-center gap-2 px-3 pt-2.5 pb-2"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <img
          src={MASCOT_URL}
          alt={brand.name}
          width={28}
          height={28}
          className="rounded-full object-cover flex-shrink-0"
          style={{ boxShadow: 'var(--shadow-sm)' }}
        />
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-semibold leading-tight truncate">
            {brand.name}
          </div>
          <div
            className="text-[9px] italic leading-tight truncate"
            style={{ color: 'var(--text-faint)' }}
          >
            {brand.slogan}
          </div>
        </div>
        <button
          onClick={toggleSidebar}
          className="h-6 w-6 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-2)' }}
          title="Toggle sidebar"
        >
          <X size={13} />
        </button>
      </div>

      {/* Action buttons — horizontal like cc-haha */}
      <div
        className="flex items-center gap-1 px-2.5 py-2"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <ActionButton
          icon={<Plus size={14} />}
          label={t('sidebar.newChat')}
          onClick={newConversation}
          primary
        />
        <IconButton
          icon={<Search size={14} />}
          onClick={() => {}}
          title="Search"
        />
        <IconButton
          icon={theme === 'dark' ? '☀' : '☾'}
          onClick={toggleTheme}
          title={t('sidebar.themeToggle')}
        />
        <NavIconButton
          href="/memory"
          icon={<History size={14} />}
          active={pathname === '/memory'}
          title={t('sidebar.nav.memory')}
        />
        <NavIconButton
          href="/tasks"
          icon={<Clock size={14} />}
          active={pathname === '/tasks'}
          title={t('sidebar.nav.tasks')}
        />
        <NavIconButton
          href="/skills"
          icon={<BookOpen size={14} />}
          active={pathname === '/skills'}
          title={t('sidebar.nav.skills')}
        />
        <NavIconButton
          href="/settings"
          icon={<Settings size={14} />}
          active={pathname === '/settings'}
          title={t('sidebar.nav.settings')}
        />
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-1.5">
        <div
          className="px-2.5 py-1 text-[10px] uppercase tracking-wide flex items-center justify-between"
          style={{ color: 'var(--text-3)' }}
        >
          <span>{expanded ? 'Sessions' : ''}</span>
          {expanded && (
            <span style={{ color: 'var(--text-faint)' }}>{conversations.length}</span>
          )}
        </div>

        <div className="px-1.5 space-y-0.5">
          {[...filtered].reverse().map((c) => (
            <div
              key={c.id}
              className="group flex items-center px-2 py-1.5 rounded-md cursor-pointer text-[12px] transition-colors"
              style={{
                background: c.id === activeId ? 'var(--surface-active)' : 'transparent',
                color: c.id === activeId ? 'var(--text)' : 'var(--text-2)',
              }}
              onClick={() => {
                setActive(c.id);
                window.location.href = '/chat';
              }}
            >
              <span className="flex-1 truncate">{c.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConversation(c.id);
                }}
                className="opacity-0 group-hover:opacity-50 hover:opacity-100"
                style={{ color: 'var(--danger)' }}
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
          {!filtered.length && (
            <div
              className="text-center text-[11px] py-3"
              style={{ color: 'var(--text-faint)' }}
            >
              {t('sidebar.emptyConversations')}
            </div>
          )}
        </div>
      </div>

      {/* Context bar */}
      <div
        className="px-3 py-2 flex items-center"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <ContextUsageIndicator />
      </div>
    </aside>
  );
}

function ActionButton({
  icon,
  label,
  onClick,
  primary = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  primary?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className="flex-1 flex items-center justify-center gap-1.5 h-7 px-2 rounded-md text-[12px] transition-colors"
      style={{
        background: primary ? 'var(--accent)' : 'var(--surface-1)',
        color: primary ? 'var(--accent-text)' : 'var(--text)',
      }}
    >
      {icon}
      {label}
    </button>
  );
}

function IconButton({
  icon,
  onClick,
  title,
}: {
  icon: React.ReactNode;
  onClick?: () => void;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="h-7 w-7 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
      style={{ color: 'var(--text-2)' }}
    >
      {icon}
    </button>
  );
}

function NavIconButton({
  href,
  icon,
  active,
  title,
}: {
  href: string;
  icon: React.ReactNode;
  active: boolean;
  title?: string;
}) {
  return (
    <Link
      href={href}
      title={title}
      className="h-7 w-7 flex items-center justify-center rounded transition-colors"
      style={{
        background: active ? 'var(--surface-active)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-2)',
      }}
    >
      {icon}
    </Link>
  );
}

function BookOpen(props: { size: number }) {
  return (
    <svg
      width={props.size}
      height={props.size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
      <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </svg>
  );
}
