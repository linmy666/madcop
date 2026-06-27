'use client';

import { useState } from 'react';
import { Check, Copy, RotateCcw, Loader2 } from 'lucide-react';
import { useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';
import MarkdownRenderer from '@/components/markdown/MarkdownRenderer';
import ThinkingBlock from './ThinkingBlock';
import ToolCallGroup from './ToolCallGroup';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

interface Props {
  message: any; // intentionally loose; we read several fields
  isStreaming?: boolean;
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export default function AssistantMessage({ message, isStreaming = false }: Props) {
  const [locale] = useLocale();
  const brand = BRAND[locale];
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content || '').then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const hasReasoning = !!(message.reasoning && message.reasoning.length > 0);
  const hasToolCalls = !!(message.toolCalls && message.toolCalls.length > 0);

  return (
    <div
      data-message-shell="assistant"
      className="group animate-slide-up"
    >
      {/* Header bar — like cc-haha */}
      <div className="flex items-center gap-2 mb-1">
        <img
          src={MASCOT_URL}
          alt={brand.name}
          width={18}
          height={18}
          className="rounded-full object-cover"
        />
        <span
          className="text-[12px] font-semibold"
          style={{ color: 'var(--text)' }}
        >
          {brand.name}
        </span>
        {message.model && (
          <span
            className="text-[10px] mono"
            style={{ color: 'var(--text-faint)' }}
          >
            {message.model}
          </span>
        )}
        {message.timestamp && (
          <span
            className="text-[10px] ml-1"
            style={{ color: 'var(--text-faint)' }}
          >
            {formatTime(message.timestamp)}
          </span>
        )}

        {/* Action bar — only on hover */}
        <div className="ml-auto flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {isStreaming ? (
            <span
              className="flex items-center gap-1 text-[10px] animate-pulse"
              style={{ color: 'var(--accent)' }}
            >
              <Loader2 size={11} className="animate-spin" />
              generating
            </span>
          ) : (
            <>
              <button
                onClick={() => {/* TODO: rewind */}}
                className="h-6 w-6 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
                style={{ color: 'var(--text-3)' }}
                title="Rewind to here"
              >
                <RotateCcw size={11} />
              </button>
              <button
                onClick={handleCopy}
                className="h-6 w-6 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
                style={{ color: copied ? 'var(--ok)' : 'var(--text-3)' }}
                title="Copy"
              >
                {copied ? <Check size={11} /> : <Copy size={11} />}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Body — left-aligned with subtle indent */}
      <div
        className="pl-7 text-[14px]"
        style={{ color: 'var(--text)' }}
      >
        {/* Thinking */}
        {hasReasoning && (
          <ThinkingBlock
            content={message.reasoning}
            isStreaming={isStreaming && !message.content}
          />
        )}

        {/* Tool calls */}
        {hasToolCalls && (
          <ToolCallGroup toolCalls={message.toolCalls} />
        )}

        {/* Main content */}
        {message.content ? (
          <div className="md-content">
            <MarkdownRenderer content={message.content} />
          </div>
        ) : isStreaming ? (
          <div className="text-[12px] shimmer-text italic">
            thinking
          </div>
        ) : null}
      </div>
    </div>
  );
}
