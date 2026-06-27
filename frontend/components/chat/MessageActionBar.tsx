'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

type Props = {
  text: string;
  timestamp?: number;
  align?: 'start' | 'end';
};

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function MessageActionBar({ text, timestamp, align = 'start' }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div
      className={`pointer-events-none mt-1.5 flex h-6 items-center gap-2 opacity-0 transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100 ${
        align === 'end' ? 'justify-end' : 'justify-start'
      }`}
    >
      {timestamp && (
        <span className="text-[10px] select-none" style={{ color: 'var(--text-faint)' }}>
          {formatTime(timestamp)}
        </span>
      )}
      {text && (
        <button
          onClick={handleCopy}
          className="flex h-6 w-6 items-center justify-center rounded-full transition-colors"
          style={{ color: 'var(--text-3)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--surface-2)';
            e.currentTarget.style.color = 'var(--text)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.color = 'var(--text-3)';
          }}
        >
          {copied ? (
            <Check size={12} style={{ color: 'var(--accent)' }} />
          ) : (
            <Copy size={12} />
          )}
        </button>
      )}
    </div>
  );
}
