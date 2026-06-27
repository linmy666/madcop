'use client';

import { useEffect, useState } from 'react';
import { X, Play, Check, AlertCircle, Loader2, Circle } from 'lucide-react';
import { useT } from '@/hooks/useTranslation';
import { apiClient } from '@/lib/api';
import type { TraceNode } from '@/types/chat';

interface Props {
  conversationId: string | null;
  open: boolean;
  onClose: () => void;
  /** When a new trace event arrives, this is the latest node. */
  latestNode: TraceNode | null;
}

const STATUS_STYLE: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  pending: { color: 'var(--text-faint)', icon: <Circle size={11} />, label: 'pending' },
  running: { color: 'var(--accent)', icon: <Loader2 size={11} className="animate-spin" />, label: 'running' },
  done: { color: 'var(--accent)', icon: <Check size={11} />, label: 'done' },
  error: { color: 'var(--danger)', icon: <AlertCircle size={11} />, label: 'error' },
  superseded: { color: 'var(--text-faint)', icon: <X size={11} />, label: 'superseded' },
};

const TYPE_LABEL: Record<string, string> = {
  user_input: 'input',
  llm_call: 'LLM',
  tool_call: 'tool',
  stream_chunk: 'stream',
};

export function TracePanel({ conversationId, open, onClose, latestNode }: Props) {
  const t = useT();
  const [nodes, setNodes] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [resumingId, setResumingId] = useState<string | null>(null);

  // Load trace when conversation changes or panel opens
  useEffect(() => {
    if (!open || !conversationId) {
      setNodes([]);
      return;
    }
    setLoading(true);
    apiClient
      .getTrace(conversationId)
      .then((data) => setNodes((data.nodes || []) as any[]))
      .catch(() => setNodes([]))
      .finally(() => setLoading(false));
  }, [open, conversationId]);

  // Update locally when a new node arrives via SSE
  useEffect(() => {
    if (!latestNode) return;
    setNodes((prev) => {
      const idx = prev.findIndex((n) => n.id === latestNode.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = latestNode as any;
        return next;
      }
      return [...prev, latestNode as any];
    });
  }, [latestNode]);

  const handleResume = async (nodeId: string) => {
    if (!conversationId) return;
    if (!confirm(t('trace.resumeConfirm'))) return;
    setResumingId(nodeId);
    try {
      await apiClient.resumeFromNode(conversationId, nodeId);
      // Refresh
      const data = await apiClient.getTrace(conversationId);
      setNodes(data.nodes || []);
    } catch (e) {
      alert('Resume failed: ' + (e as Error).message);
    } finally {
      setResumingId(null);
    }
  };

  if (!open) return null;

  return (
    <aside
      className="flex flex-col border-l animate-slide-up"
      style={{
        width: '360px',
        background: 'var(--surface)',
        borderColor: 'var(--border)',
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div className="flex items-center px-4 h-10 border-b" style={{ borderColor: 'var(--border)' }}>
        <h2 className="text-[13px] font-semibold flex-1">{t('trace.title')}</h2>
        <button onClick={onClose} className="p-1 rounded hover:bg-[var(--surface-2)]">
          <X size={14} style={{ color: 'var(--text-2)' }} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading && (
          <div className="text-center text-[12px] py-6" style={{ color: 'var(--text-3)' }}>
            <Loader2 size={14} className="animate-spin inline mr-1" />
            {t('trace.loading')}
          </div>
        )}
        {!loading && nodes.length === 0 && (
          <div className="text-center text-[12px] py-6" style={{ color: 'var(--text-faint)' }}>
            {t('trace.empty')}
          </div>
        )}
        {nodes.map((node) => {
          const status = STATUS_STYLE[node.status] || STATUS_STYLE.pending;
          const typeLabel = TYPE_LABEL[node.node_type] || node.node_type;
          return (
            <div
              key={node.id}
              className="mb-2 rounded-lg border overflow-hidden animate-fade-in"
              style={{
                borderColor: node.status === 'running' ? 'var(--accent)' : 'var(--border)',
                background: 'var(--surface-2)',
                marginLeft: node.depth * 12,
              }}
            >
              {/* Node header */}
              <div className="flex items-center gap-2 px-3 py-2 text-[12px]">
                <span style={{ color: status.color }}>{status.icon}</span>
                <span
                  className="text-[10px] uppercase tracking-wide mono"
                  style={{ color: 'var(--text-3)' }}
                >
                  {typeLabel}
                </span>
                <span className="flex-1 truncate" style={{ color: 'var(--text)' }}>
                  {node.label}
                </span>
                <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
                  #{node.id.slice(0, 6)}
                </span>
              </div>

              {/* Node body */}
              {(node.input || node.output) && (
                <div className="px-3 py-2 text-[11px] border-t" style={{ borderColor: 'var(--border)' }}>
                  {node.input && (
                    <details>
                      <summary className="cursor-pointer select-none" style={{ color: 'var(--text-3)' }}>
                        input
                      </summary>
                      <pre className="mt-1 whitespace-pre-wrap break-all text-[10px] mono" style={{ color: 'var(--text-2)' }}>
                        {node.input.length > 400 ? node.input.slice(0, 400) + '...' : node.input}
                      </pre>
                    </details>
                  )}
                  {node.output && (
                    <details>
                      <summary className="cursor-pointer select-none mt-1" style={{ color: 'var(--text-3)' }}>
                        output
                      </summary>
                      <pre className="mt-1 whitespace-pre-wrap break-all text-[10px] mono" style={{ color: 'var(--text-2)' }}>
                        {node.output.length > 400 ? node.output.slice(0, 400) + '...' : node.output}
                      </pre>
                    </details>
                  )}
                </div>
              )}

              {/* Resume button — only for done nodes that have children */}
              {node.status === 'done' && (
                <button
                  onClick={() => handleResume(node.id)}
                  disabled={resumingId === node.id}
                  className="w-full flex items-center justify-center gap-1 py-1.5 text-[11px] border-t transition-colors hover:bg-[var(--surface)] disabled:opacity-50"
                  style={{ borderColor: 'var(--border)', color: 'var(--accent)' }}
                >
                  {resumingId === node.id ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : (
                    <Play size={11} fill="currentColor" />
                  )}
                  {t('trace.resume')}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
