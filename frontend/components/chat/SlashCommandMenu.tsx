'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { useLocale } from '@/hooks/useTranslation';

interface SlashCommand {
  name: string;
  descEn: string;
  descZh: string;
  icon: string;
  action: () => void;
}

interface Props {
  visible: boolean;
  onSelect: (cmd: SlashCommand | null) => void;
  onClose: () => void;
}

export function SlashCommandMenu({ visible, onSelect, onClose }: Props) {
  const [highlight, setHighlight] = useState(0);
  const [locale] = useLocale();
  const { conversations, activeId, deleteConversation, newConversation } = useChatStore();

  const commands: SlashCommand[] = [
    {
      name: 'new',
      descEn: 'Start a new conversation',
      descZh: '开始新对话',
      icon: '+',
      action: () => newConversation(),
    },
    {
      name: 'clear',
      descEn: 'Clear current conversation',
      descZh: '清空当前对话',
      icon: 'x',
      action: () => {
        if (activeId) deleteConversation(activeId);
        newConversation();
      },
    },
    {
      name: 'settings',
      descEn: 'Open settings',
      descZh: '打开设置',
      icon: '@',
      action: () => { window.location.href = '/settings'; },
    },
    {
      name: 'memory',
      descEn: 'View memories',
      descZh: '查看记忆',
      icon: 'M',
      action: () => { window.location.href = '/memory'; },
    },
    {
      name: 'tasks',
      descEn: 'View scheduled tasks',
      descZh: '查看定时任务',
      icon: 'T',
      action: () => { window.location.href = '/tasks'; },
    },
  ];

  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setHighlight((h) => Math.min(h + 1, commands.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setHighlight((h) => Math.max(h - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const cmd = commands[highlight];
        cmd.action();
        onClose();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [visible, highlight, commands.length]);

  if (!visible) return null;

  return (
    <div
      className="absolute bottom-full left-0 right-0 mb-2 max-w-md rounded-xl border overflow-hidden animate-slide-up"
      style={{
        background: 'var(--surface)',
        borderColor: 'var(--border)',
        boxShadow: 'var(--shadow-lg)',
        zIndex: 50,
      }}
    >
      <div className="py-1">
        {commands.map((cmd, i) => (
          <div
            key={cmd.name}
            className={`flex items-center gap-3 px-3 py-2 cursor-pointer text-sm transition-colors ${
              i === highlight ? '' : ''
            }`}
            style={{
              background: i === highlight ? 'var(--surface-3)' : 'transparent',
            }}
            onMouseEnter={() => setHighlight(i)}
            onClick={() => {
              cmd.action();
              onClose();
            }}
          >
            <span
              className="flex h-6 w-6 items-center justify-center rounded text-[11px] font-mono"
              style={{ background: 'var(--surface-2)', color: 'var(--accent)' }}
            >
              {cmd.icon}
            </span>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-[13px]" style={{ color: 'var(--text)' }}>
                /{cmd.name}
              </div>
              <div className="text-[11px]" style={{ color: 'var(--text-3)' }}>
                {locale === 'zh' ? cmd.descZh : cmd.descEn}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
