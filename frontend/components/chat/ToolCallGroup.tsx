'use client';

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Wrench,
  CheckCircle2,
  Loader2,
} from 'lucide-react';
import type { ToolCall } from '@/types/chat';

// ── Single tool call ───────────────────────────────────────────
function ToolCallBlock({ call }: { call: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const hasResult = call.result !== undefined && call.result !== null;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ background: 'var(--surface)' }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center gap-2 px-3 py-2 text-[13px] transition-colors hover:bg-[var(--surface-2)]"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-[var(--text-3)]" />
        ) : (
          <ChevronRight size={14} className="text-[var(--text-3)]" />
        )}
        <Wrench size={13} style={{ color: 'var(--accent)' }} />
        <span className="font-mono font-medium" style={{ color: 'var(--accent)' }}>
          {call.name}
        </span>
        {hasResult ? (
          <CheckCircle2 size={13} className="text-[var(--accent)]" />
        ) : (
          <Loader2 size={13} className="animate-spin text-[var(--text-3)]" />
        )}
        {!expanded && call.args && (
          <span className="ml-1 truncate font-mono text-[11px] text-[var(--text-3)]">
            {JSON.stringify(call.args).slice(0, 80)}
          </span>
        )}
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-[var(--border)] px-3 py-2 space-y-2">
          {/* Arguments */}
          {call.args && Object.keys(call.args).length > 0 && (
            <div>
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-3)]">
                参数
              </div>
              <pre
                className="overflow-x-auto rounded p-2 text-[12px] font-mono"
                style={{ background: 'var(--code-bg)', color: 'var(--code-fg)' }}
              >
                {JSON.stringify(call.args, null, 2)}
              </pre>
            </div>
          )}

          {/* Result */}
          {hasResult && (
            <div>
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-3)]">
                结果
              </div>
              <pre
                className="overflow-x-auto rounded p-2 text-[12px] font-mono max-h-[200px] overflow-y-auto"
                style={{ background: 'var(--code-bg)', color: 'var(--code-fg)' }}
              >
                {call.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Group wrapper ──────────────────────────────────────────────
interface ToolCallGroupProps {
  calls: ToolCall[];
}

export default function ToolCallGroup({ calls }: ToolCallGroupProps) {
  const [expanded, setExpanded] = useState(false);

  if (!calls || calls.length === 0) return null;

  // Single call: render directly without group wrapper
  if (calls.length === 1) {
    return (
      <div className="my-2">
        <ToolCallBlock call={calls[0]} />
      </div>
    );
  }

  // Multiple calls: collapse into summary
  const allDone = calls.every((c) => c.result !== undefined && c.result !== null);

  return (
    <div className="my-2">
      {/* Summary line */}
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-[13px] transition-colors hover:bg-[var(--surface-2)]"
        style={{ background: 'var(--surface)' }}
      >
        {expanded ? (
          <ChevronDown size={14} className="text-[var(--text-3)]" />
        ) : (
          <ChevronRight size={14} className="text-[var(--text-3)]" />
        )}
        <Wrench size={13} style={{ color: 'var(--accent)' }} />
        <span className="text-[var(--text-2)]">
          调用了 <strong style={{ color: 'var(--accent)' }}>{calls.length}</strong> 个工具
        </span>
        {allDone ? (
          <CheckCircle2 size={13} className="ml-auto text-[var(--accent)]" />
        ) : (
          <Loader2 size={13} className="ml-auto animate-spin text-[var(--text-3)]" />
        )}
      </button>

      {/* Expanded individual calls */}
      {expanded && (
        <div className="mt-1.5 space-y-1.5 animate-slide-up">
          {calls.map((call) => (
            <ToolCallBlock key={call.id} call={call} />
          ))}
        </div>
      )}
    </div>
  );
}
