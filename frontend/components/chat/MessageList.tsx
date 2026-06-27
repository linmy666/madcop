'use client';

import { useEffect, useRef } from 'react';
import type { Message } from '@/types/chat';
import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

interface MessageListProps {
  messages: Message[];
  /** ID of the message currently being streamed (if any). */
  streamingId?: string | null;
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 animate-fade-in">
      <img
        src={MASCOT_URL}
        alt="madcop"
        width={72}
        height={72}
        className="rounded-2xl border border-[var(--border)] shadow-lg"
        style={{ boxShadow: 'var(--shadow-lg)' }}
      />
      <div className="text-center">
        <h2 className="text-lg font-bold text-[var(--text)]">madcop</h2>
        <p className="mt-1 text-[13px] text-[var(--text-2)]">
          有什么可以帮你的？
        </p>
      </div>
      {/* Suggestion chips */}
      <div className="flex flex-wrap justify-center gap-2 max-w-md">
        {[
          '帮我分析一下这段代码',
          '今天的天气怎么样？',
          '写一个 Python 排序脚本',
          '解释一下量子计算',
        ].map((s) => (
          <span
            key={s}
            className="cursor-default rounded-full border border-[var(--border)] px-3 py-1 text-[12px] text-[var(--text-2)] transition-colors hover:bg-[var(--surface-2)]"
            style={{ background: 'var(--surface)' }}
          >
            {s}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function MessageList({ messages, streamingId }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, streamingId]);

  if (!messages || messages.length === 0) {
    return (
      <div
        ref={scrollRef}
        className="h-full overflow-y-auto px-4 py-6"
      >
        <EmptyState />
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((msg) => {
          if (msg.role === 'user') {
            return <UserMessage key={msg.id} message={msg} />;
          }
          if (msg.role === 'assistant') {
            return (
              <AssistantMessage
                key={msg.id}
                message={msg}
                isStreaming={msg.id === streamingId}
              />
            );
          }
          // system / tool roles: skip direct rendering
          return null;
        })}
        {/* Sentinel for scroll */}
        <div ref={bottomRef} className="h-px" />
      </div>
    </div>
  );
}
