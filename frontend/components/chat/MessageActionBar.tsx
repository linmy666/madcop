'use client';

import { useState } from 'react';
import { Check, Copy, RotateCcw } from 'lucide-react';

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
      className={`pointer-events-none mt-1 flex h-6 items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100 ${
        align === 'end' ? 'justify-end' : 'justify-start'
      }`}
    >
      {timestamp && (
        <span
          className="text-[10px] select-none"
          style={{ color: 'var(--text-faint)' }}
        >
          {formatTime(timestamp)}
        </span>
      )}
      <button
        onClick={handleCopy}
        className="h-6 w-6 flex items-center justify-center rounded transition-colors"
        style={{ color: copied ? 'var(--ok)' : 'var(--text-3)' }}
        title="Copy"
      >
        {copied ? <Check size={11} /> : <Copy size={11} />}
      </button>
      <button
        className="h-6 w-6 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
        style={{ color: 'var(--text-3)' }}
        title="Rewind"
      >
        <RotateCcw size={11} />
      </button>
    </div>
  );
}
