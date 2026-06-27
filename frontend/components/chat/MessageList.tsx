'use client';

import { useEffect, useRef } from 'react';
import type { Message } from '@/types/chat';
import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';
import { useT, useLocale } from '@/hooks/useTranslation';
import { BRAND } from '@/lib/i18n';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

interface MessageListProps {
  messages: Message[];
  streamingId?: string | null;
}

function EmptyState() {
  const t = useT();
  const [locale] = useLocale();
  const brand = BRAND[locale];
  const suggestions =
    locale === 'zh'
      ? [
          '如何写一个 Python 测试函数？',
          '上海今天天气怎么样？',
          '解释一下 JWT 鉴权原理',
          '帮我写一个 SQL 优化建议',
        ]
      : [
          'How to write a Python test function?',
          "What's the weather in Shanghai today?",
          'Explain JWT authentication',
          'Suggest a SQL optimization',
        ];

  return (
    <div className="flex h-full flex-col items-center justify-center gap-6 animate-fade-in px-6">
      <img
        src={MASCOT_URL}
        alt={brand.name}
        width={88}
        height={88}
        className="rounded-full"
        style={{ boxShadow: 'var(--shadow-lg)' }}
      />
      <div className="text-center max-w-md">
        <h2 className="text-xl font-semibold" style={{ color: 'var(--text)' }}>
          {brand.name}
        </h2>
        <p
          className="mt-1.5 text-[12px] italic"
          style={{ color: 'var(--text-faint)' }}
        >
          {brand.slogan}
        </p>
        <p className="mt-5 text-[13px]" style={{ color: 'var(--text-2)' }}>
          {t('welcome.title')}
        </p>
        <p className="mt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
          {t('welcome.subtitle')}
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2 max-w-lg">
        {suggestions.map((s) => (
          <span
            key={s}
            className="px-3 py-1.5 text-[12px] rounded-full border cursor-default transition-colors hover:bg-[var(--surface-hover)]"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              color: 'var(--text-2)',
            }}
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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, streamingId]);

  if (!messages || messages.length === 0) {
    return (
      <div ref={scrollRef} className="h-full overflow-y-auto">
        <EmptyState />
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto py-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-3 px-4">
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
          return null;
        })}
        <div ref={bottomRef} className="h-px" />
      </div>
    </div>
  );
}
