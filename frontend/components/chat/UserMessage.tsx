'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import type { Message } from '@/types/chat';

interface UserMessageProps {
  message: Message;
}

function formatTime(ts?: number): string {
  if (!ts) return '';
  return new Date(ts).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function UserMessage({ message }: UserMessageProps) {
  const [copied, setCopied] = useState(false);
  const [hovered, setHovered] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div
      className="flex justify-end animate-slide-up"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="flex max-w-[80%] flex-col items-end gap-1">
        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 justify-end">
            {message.attachments.map((att, i) =>
              att.isImage ? (
                <img
                  key={i}
                  src={att.data}
                  alt={att.name}
                  className="max-h-32 max-w-32 rounded-lg border border-[var(--border)] object-cover"
                />
              ) : (
                <div
                  key={i}
                  className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-2.5 py-1.5 text-xs"
                  style={{ background: 'var(--surface)' }}
                >
                  <span className="text-[var(--text-2)]">📎</span>
                  <span className="text-[var(--text)]">{att.name}</span>
                </div>
              ),
            )}
          </div>
        )}

        {/* Bubble */}
        <div className="flex items-center gap-2">
          {hovered && (
            <div className="flex items-center gap-1 text-[var(--text-3)] animate-fade-in">
              <span className="text-[11px]">{formatTime(message.timestamp)}</span>
              <button
                onClick={handleCopy}
                className="rounded p-1 transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                title="复制"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
              </button>
            </div>
          )}

          <div
            className="px-4 py-2.5 text-[14px] leading-7 whitespace-pre-wrap break-words"
            style={{
              background: 'var(--surface-user-msg)',
              color: 'var(--text)',
              borderRadius: '18px 4px 18px 18px',
            }}
          >
            {message.content}
          </div>
        </div>
      </div>
    </div>
  );
}
