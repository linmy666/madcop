'use client';

import { useState } from 'react';
import { ChevronRight, Loader2, Check, X, FileText, Search, Globe, Calculator, Box, Edit3, BookOpen, Cpu } from 'lucide-react';

interface ToolCall {
  id: string;
  name: string;
  args?: Record<string, unknown>;
  result?: string | null;
}

const ICONS: Record<string, any> = {
  web_search: Globe,
  get_weather: Globe,
  web_fetch: Globe,
  read_file: FileText,
  write_file: Edit3,
  edit_file: Edit3,
  bash: Cpu,
  search: Search,
  math: Calculator,
  default: Box,
};

const LABELS: Record<string, string> = {
  web_search: 'Web Search',
  get_weather: 'Weather',
  web_fetch: 'Web Fetch',
  read_file: 'Read File',
  write_file: 'Write File',
  edit_file: 'Edit File',
  bash: 'Bash',
};

interface Props {
  toolCalls: ToolCall[];
}

export default function ToolCallGroup({ toolCalls }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (toolCalls.length === 0) return null;
  if (toolCalls.length === 1) {
    return <ToolCallRow call={toolCalls[0]} />;
  }

  return (
    <div
      className="mb-2 rounded-lg border overflow-hidden"
      style={{
        borderColor: 'var(--border)',
        background: 'var(--surface-1)',
      }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] hover:bg-[var(--surface-hover)] transition-colors"
      >
        <ChevronRight
          size={12}
          className={expanded ? 'rotate-90' : ''}
          style={{ color: 'var(--text-3)', transition: 'transform .15s' }}
        />
        <span
          className="font-medium"
          style={{ color: 'var(--text-2)' }}
        >
          {toolCalls.length} tool calls
        </span>
      </button>
      {expanded && (
        <div className="border-t" style={{ borderColor: 'var(--border)' }}>
          {toolCalls.map((c) => (
            <ToolCallRow key={c.id} call={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolCallRow({ call }: { call: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = ICONS[call.name] || ICONS.default;
  const label = LABELS[call.name] || call.name;
  const isDone = call.result !== undefined && call.result !== null;
  const argsStr = call.args ? JSON.stringify(call.args) : '';
  const argsShort = argsStr.length > 100 ? argsStr.slice(0, 100) + '...' : argsStr;

  return (
    <div
      className="border-b last:border-b-0"
      style={{ borderColor: 'var(--border)' }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] hover:bg-[var(--surface-hover)] transition-colors"
      >
        <Icon size={12} style={{ color: 'var(--text-2)' }} />
        <span className="font-medium" style={{ color: 'var(--text-2)' }}>
          {label}
        </span>
        {argsShort && (
          <span
            className="flex-1 truncate font-mono text-[10px]"
            style={{ color: 'var(--text-3)' }}
          >
            {argsShort}
          </span>
        )}
        <span className="flex-shrink-0">
          {isDone ? (
            <Check size={11} style={{ color: 'var(--ok)' }} />
          ) : (
            <Loader2 size={11} className="animate-spin" style={{ color: 'var(--accent)' }} />
          )}
        </span>
      </button>
      {expanded && call.result && (
        <div
          className="px-3 py-2 text-[11px] border-t font-mono whitespace-pre-wrap max-h-40 overflow-y-auto"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface-code)',
            color: 'var(--text-2)',
          }}
        >
          {call.result.length > 600 ? call.result.slice(0, 600) + '...' : call.result}
        </div>
      )}
    </div>
  );
}
