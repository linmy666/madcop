'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import type { Message } from '@/types/chat';
import MarkdownRenderer from '@/components/markdown/MarkdownRenderer';
import ThinkingBlock from './ThinkingBlock';
import ToolCallGroup from './ToolCallGroup';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

interface AssistantMessageProps {
  message: Message;
  /** true while this message is actively receiving streamed tokens. */
  isStreaming?: boolean;
}

export default function AssistantMessage({
  message,
  isStreaming = false,
}: AssistantMessageProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const hasContent = message.content && message.content.length > 0;
  const hasReasoning = message.reasoning && message.reasoning.length > 0;
  const hasToolCalls = message.toolCalls && message.toolCalls.length > 0;

  return (
    <div className="group flex gap-2.5 animate-slide-up">
      {/* Avatar */}
      <div className="flex-shrink-0 pt-0.5">
        <img
          src={MASCOT_URL}
          alt="madcop"
          width={28}
          height={28}
          className="h-7 w-7 rounded-full border border-[var(--border)] object-cover"
        />
      </div>

      {/* Content column */}
      <div className="min-w-0 flex-1">
        {/* Name label */}
        <div className="mb-0.5 flex items-center gap-1.5">
          <span className="text-[13px] font-semibold text-[var(--text)]">madcop</span>
          {message.model && (
            <span className="text-[11px] text-[var(--text-3)]">{message.model}</span>
          )}
          {/* Copy button on hover */}
          <button
            onClick={handleCopy}
            className="ml-auto flex items-center gap-1 rounded p-1 text-[var(--text-3)] opacity-0 transition-all hover:bg-[var(--surface-2)] hover:text-[var(--text)] group-hover:opacity-100"
            title="复制"
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
        </div>

        {/* Reasoning / thinking */}
        {hasReasoning && (
          <ThinkingBlock
            content={message.reasoning!}
            isStreaming={isStreaming && !hasContent}
          />
        )}

        {/* Tool calls */}
        {hasToolCalls && <ToolCallGroup calls={message.toolCalls!} />}

        {/* Main content */}
        {hasContent ? (
          <div className="text-[var(--text)]">
            <MarkdownRenderer content={message.content} />
          </div>
        ) : isStreaming && !hasReasoning && !hasToolCalls ? (
          /* Shimmer "思考中" placeholder */
          <div className="py-1">
            <span className="shimmer-text text-[14px] font-medium">思考中</span>
          </div>
        ) : null}

        {/* Streaming cursor */}
        {isStreaming && hasContent && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-[var(--accent)] align-middle" />
        )}
      </div>
    </div>
  );
}
