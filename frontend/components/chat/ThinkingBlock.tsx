'use client';

import { useState } from 'react';
import { ChevronRight, Brain } from 'lucide-react';
import { useT } from '@/hooks/useTranslation';
import MarkdownRenderer from '@/components/markdown/MarkdownRenderer';

interface ThinkingBlockProps {
  content: string;
  isStreaming?: boolean;
  defaultCollapsed?: boolean;
}

export default function ThinkingBlock({
  content,
  isStreaming = false,
  defaultCollapsed = true,
}: ThinkingBlockProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const t = useT();

  return (
    <div
      className="mb-2 rounded-md border overflow-hidden animate-fade-in"
      style={{
        background: 'var(--reasoning-bg)',
        borderColor: 'var(--reasoning-border)',
      }}
    >
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium transition-colors hover:bg-[var(--surface-hover)]"
        style={{ color: 'var(--text-2)' }}
      >
        {collapsed ? <ChevronRight size={11} /> : <ChevronRight size={11} className="rotate-90" style={{ transition: 'transform .15s' }} />}
        <Brain size={11} />
        <span className={`italic ${isStreaming ? 'shimmer-text' : ''}`}>
          {t('msg.thinking')}
        </span>
        {isStreaming && (
          <span
            className="ml-1 text-[10px] flex items-center gap-1"
            style={{ color: 'var(--accent)' }}
          >
            <span
              className="inline-block h-1.5 w-1.5 rounded-full animate-pulse"
              style={{ background: 'var(--accent)' }}
            />
            {t('msg.streaming')}
          </span>
        )}
      </button>

      {!collapsed && (
        <div
          className="px-3 py-2 text-[12px] italic border-t max-h-72 overflow-y-auto"
          style={{
            borderColor: 'var(--reasoning-border)',
            color: 'var(--text-3)',
          }}
        >
          <MarkdownRenderer content={content || '...'} variant="compact" />
        </div>
      )}
    </div>
  );
}
