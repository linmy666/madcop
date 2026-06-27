'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import MessageList from '@/components/chat/MessageList';
import ChatInput from '@/components/chat/ChatInput';
import { useChatStore } from '@/stores/chatStore';
import { streamChat } from '@/lib/api';
import type { Message, SSEEvent } from '@/types/chat';
import type { TraceNode } from '@/types/chat';
import { TracePanel } from '@/components/chat/TracePanel';
import { useT } from '@/hooks/useTranslation';
import { Activity } from 'lucide-react';

export default function ChatPage() {
  const conversations = useChatStore((s) => s.conversations);
  const activeId = useChatStore((s) => s.activeId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const temperature = useChatStore((s) => s.temperature);
  const t = useT();

  const [traceOpen, setTraceOpen] = useState(false);
  const [latestTraceNode, setLatestTraceNode] = useState<TraceNode | null>(null);
  const startTimeRef = useRef<number>(0);

  // Persisted conversation id (used as trace id)
  const convId = activeId || 'default';

  const conv = conversations.find((c) => c.id === activeId);

  const handleSend = useCallback(
    async (
      text: string,
      attachments: Array<{ name: string; data: string; isImage: boolean }>,
    ) => {
      const store = useChatStore.getState();
      if (store.isStreaming) return;
      if (!text && !attachments.length) return;

      // Ensure conversation exists
      if (!store.activeId) {
        store.newConversation();
      }
      const convId = useChatStore.getState().activeId!;

      // Add user message
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: 'user',
        content:
          text +
          (attachments.length
            ? `\n\n[Attachment: ${attachments.map((a) => a.name).join(', ')}]`
            : ''),
        timestamp: Date.now(),
        attachments: attachments.map((a) => ({
          ...a,
          type: a.isImage ? 'image' : 'file',
        })),
      };
      store.addMessage(convId, userMsg);

      // Update title if first message
      const updatedConv = useChatStore
        .getState()
        .conversations.find((c) => c.id === convId);
      if (
        updatedConv &&
        updatedConv.messages.filter((m) => m.role === 'user').length === 1
      ) {
        useChatStore.setState((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId ? { ...c, title: text.slice(0, 30) } : c,
          ),
        }));
      }

      // Add assistant placeholder
      const assistantId = `a-${Date.now()}`;
      store.addMessage(convId, {
        id: assistantId,
        role: 'assistant',
        content: '',
        reasoning: '',
        toolCalls: [],
      });
      store.setStreaming(true);
      startTimeRef.current = Date.now();

      try {
        // Build message history (exclude the assistant placeholder)
        const currentConv = useChatStore
          .getState()
          .conversations.find((c) => c.id === convId)!;
        const histMessages = currentConv.messages
          .filter((m) => m.id !== assistantId)
          .map((m) => {
            if (m.attachments?.some((a) => a.isImage)) {
              const content: unknown[] = [{ type: 'text', text: m.content }];
              m.attachments
                .filter((a) => a.isImage)
                .forEach((a) => {
                  content.push({ type: 'image_url', image_url: { url: a.data } });
                });
              return { role: m.role, content };
            }
            return { role: m.role, content: m.content };
          });

        for await (const raw of streamChat(histMessages, temperature, convId)) {
          const evt = raw as SSEEvent;
          const s = useChatStore.getState();
          const current = s.conversations
            .find((c) => c.id === convId)
            ?.messages.find((m) => m.id === assistantId);
          if (!current) break;

          if (evt.type === 'trace' && evt.node) {
            setLatestTraceNode(evt.node);
            // Auto-open trace panel on first trace event
            if (!traceOpen) setTraceOpen(true);
          } else if (evt.type === 'reasoning') {
            s.updateMessage(convId, assistantId, {
              reasoning: (current.reasoning || '') + (evt.content || ''),
            });
          } else if (evt.type === 'text') {
            s.updateMessage(convId, assistantId, {
              content: (current.content || '') + (evt.content || ''),
            });
          } else if (evt.type === 'tool') {
            s.updateMessage(convId, assistantId, {
              toolCalls: [
                ...(current.toolCalls || []),
                {
                  id: `tc-${Date.now()}`,
                  name: evt.name || '',
                  args: evt.args || {},
                  result: null,
                },
              ],
            });
          } else if (evt.type === 'tool_result') {
            const calls = [...(current.toolCalls || [])];
            const last = calls[calls.length - 1];
            if (last) last.result = evt.result || '';
            s.updateMessage(convId, assistantId, { toolCalls: calls });
          } else if (evt.type === 'done') {
            s.updateMessage(convId, assistantId, { model: evt.model });
          } else if (evt.type === 'error') {
            s.updateMessage(convId, assistantId, {
              content: (current.content || '') + `\n\nError: ${evt.message}`,
            });
          }
        }
      } catch (e) {
        const s = useChatStore.getState();
        const current = s.conversations
          .find((c) => c.id === convId)
          ?.messages.find((m) => m.id === assistantId);
        s.updateMessage(convId, assistantId, {
          content:
            (current?.content || '') +
            `\n\nNetwork error: ${(e as Error).message}`,
        });
      } finally {
        useChatStore.getState().setStreaming(false);
      }
    },
    [isStreaming, temperature],
  );

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Trace toggle button */}
            <div className="px-4 pt-2 flex justify-end">
              <button
                onClick={() => setTraceOpen((o) => !o)}
                className="flex items-center gap-1 px-2 py-1 text-[11px] rounded transition-colors"
                style={{
                  background: traceOpen ? 'var(--accent-dim)' : 'transparent',
                  color: traceOpen ? 'var(--accent)' : 'var(--text-3)',
                }}
              >
                <Activity size={11} />
                {t('trace.title')}
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <MessageList messages={conv?.messages || []} />
            </div>
            <ChatInput
              onSend={(text, attachments) => handleSend(text, attachments)}
              disabled={isStreaming}
              isStreaming={isStreaming}
            />
          </div>
          <TracePanel
            conversationId={convId}
            open={traceOpen}
            onClose={() => setTraceOpen(false)}
            latestNode={latestTraceNode}
          />
        </div>
      </div>
    </AppShell>
  );
}
