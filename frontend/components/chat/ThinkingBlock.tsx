'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
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
      className="my-1.5 rounded-lg border overflow-hidden animate-fade-in"
      style={{ background: 'var(--reasoning-bg)', borderColor: 'var(--reasoning-border)' }}
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[12px] transition-colors hover:bg-[var(--surface-2)]"
        style={{ color: 'var(--text-3)' }}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
        <span className={`font-medium italic ${isStreaming ? 'thinking-dots' : ''}`}>
          {t('msg.thinking')}
        </span>
        {isStreaming && (
          <span className="ml-auto flex items-center gap-1 text-[10px]" style={{ color: 'var(--accent)' }}>
            <span className="inline-block h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: 'var(--accent)' }} />
            {t('msg.streaming')}
          </span>
        )}
      </button>

      {/* Content */}
      {!collapsed && (
        <div className="max-h-[300px] overflow-y-auto border-t px-3 py-2"
          style={{ borderColor: 'var(--reasoning-border)' }}
        >
          <div className="text-[12px] italic whitespace-pre-wrap" style={{ color: 'var(--text-3)' }}>
            <MarkdownRenderer content={content || '...'} variant="compact" />
          </div>
        </div>
      )}
    </div>
  );
}
