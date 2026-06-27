'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Brain } from 'lucide-react';
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

  return (
    <div
      className="my-2 rounded-lg border border-[var(--border)] overflow-hidden animate-fade-in"
      style={{ background: 'var(--moon-bg)' }}
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-[13px] font-medium transition-colors hover:bg-[var(--surface-2)]"
        style={{ color: 'var(--moon)' }}
      >
        {collapsed ? (
          <ChevronRight size={14} />
        ) : (
          <ChevronDown size={14} />
        )}
        <Brain size={14} />
        <span className={isStreaming ? 'thinking-dots' : ''}>推理过程</span>
        {isStreaming && (
          <span className="ml-auto flex items-center gap-1 text-[11px] text-[var(--text-3)]">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--moon)] animate-pulse" />
            生成中
          </span>
        )}
      </button>

      {/* Content */}
      {!collapsed && (
        <div
          className="max-h-[300px] overflow-y-auto border-t border-[var(--border)] px-3 py-2"
        >
          <div className="font-mono text-[13px] text-[var(--text-2)] whitespace-pre-wrap">
            <MarkdownRenderer content={content || '（无内容）'} />
          </div>
        </div>
      )}
    </div>
  );
}
