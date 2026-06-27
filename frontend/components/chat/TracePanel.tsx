'use client';

import { useEffect, useState } from 'react';
import { X, Play, Check, AlertCircle, Loader2, Circle, Activity } from 'lucide-react';
import { useT } from '@/hooks/useTranslation';
import { apiClient } from '@/lib/api';

interface Props {
  conversationId: string | null;
  open: boolean;
  onClose: () => void;
  latestNode: any;
}

const STATUS: Record<string, { color: string; icon: any; label: string }> = {
  pending: { color: 'var(--text-faint)', icon: Circle, label: 'pending' },
  running: { color: 'var(--accent)', icon: Loader2, label: 'running' },
  done: { color: 'var(--ok)', icon: Check, label: 'done' },
  error: { color: 'var(--danger)', icon: AlertCircle, label: 'error' },
  superseded: { color: 'var(--text-faint)', icon: X, label: 'superseded' },
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
      const data = await apiClient.getTrace(conversationId);
      setNodes((data.nodes || []) as any[]);
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
        width: '320px',
        background: 'var(--surface)',
        borderColor: 'var(--border)',
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div
        className="flex items-center px-3 h-9 border-b"
        style={{ borderColor: 'var(--border)' }}
      >
        <Activity size={13} style={{ color: 'var(--accent)' }} className="mr-1.5" />
        <h2 className="text-[12px] font-semibold flex-1">{t('trace.title')}</h2>
        <button
          onClick={onClose}
          className="h-6 w-6 flex items-center justify-center rounded hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-2)' }}
        >
          <X size={13} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-2">
        {loading && (
          <div
            className="text-center text-[11px] py-6"
            style={{ color: 'var(--text-3)' }}
          >
            <Loader2 size={12} className="animate-spin inline mr-1" />
            {t('trace.loading')}
          </div>
        )}
        {!loading && nodes.length === 0 && (
          <div
            className="text-center text-[11px] py-6"
            style={{ color: 'var(--text-faint)' }}
          >
            {t('trace.empty')}
          </div>
        )}
        {nodes.map((node) => {
          const statusInfo = STATUS[node.status] || STATUS.pending;
          const StatusIcon = statusInfo.icon;
          const typeLabel = TYPE_LABEL[node.node_type] || node.node_type;
          return (
            <div
              key={node.id}
              className="mb-1.5 rounded-md border overflow-hidden animate-fade-in"
              style={{
                borderColor: node.status === 'running' ? 'var(--accent)' : 'var(--border)',
                background: 'var(--surface-1)',
                marginLeft: node.depth * 10,
              }}
            >
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px]">
                <StatusIcon
                  size={10}
                  className={node.status === 'running' ? 'animate-spin' : ''}
                  style={{ color: statusInfo.color }}
                />
                <span
                  className="text-[9px] uppercase tracking-wide mono"
                  style={{ color: 'var(--text-3)' }}
                >
                  {typeLabel}
                </span>
                <span
                  className="flex-1 truncate"
                  style={{ color: 'var(--text)' }}
                >
                  {node.label}
                </span>
                <span
                  className="text-[9px] mono"
                  style={{ color: 'var(--text-faint)' }}
                >
                  #{node.id.slice(0, 6)}
                </span>
              </div>

              {(node.input || node.output) && (
                <div
                  className="px-2.5 py-1.5 text-[10px] border-t"
                  style={{ borderColor: 'var(--border)' }}
                >
                  {node.input && (
                    <details>
                      <summary
                        className="cursor-pointer select-none"
                        style={{ color: 'var(--text-3)' }}
                      >
                        input
                      </summary>
                      <pre
                        className="mt-1 whitespace-pre-wrap break-all text-[10px] mono"
                        style={{ color: 'var(--text-2)' }}
                      >
                        {node.input.length > 400
                          ? node.input.slice(0, 400) + '...'
                          : node.input}
                      </pre>
                    </details>
                  )}
                  {node.output && (
                    <details>
                      <summary
                        className="cursor-pointer select-none mt-1"
                        style={{ color: 'var(--text-3)' }}
                      >
                        output
                      </summary>
                      <pre
                        className="mt-1 whitespace-pre-wrap break-all text-[10px] mono"
                        style={{ color: 'var(--text-2)' }}
                      >
                        {node.output.length > 400
                          ? node.output.slice(0, 400) + '...'
                          : node.output}
                      </pre>
                    </details>
                  )}
                </div>
              )}

              {node.status === 'done' && (
                <button
                  onClick={() => handleResume(node.id)}
                  disabled={resumingId === node.id}
                  className="w-full flex items-center justify-center gap-1 py-1 text-[10px] border-t transition-colors hover:bg-[var(--surface)] disabled:opacity-50"
                  style={{
                    borderColor: 'var(--border)',
                    color: 'var(--accent)',
                  }}
                >
                  {resumingId === node.id ? (
                    <Loader2 size={10} className="animate-spin" />
                  ) : (
                    <Play size={10} fill="currentColor" />
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
