'use client';

import { AppShell } from '@/components/layout/AppShell';
import MessageList from '@/components/chat/MessageList';
import ChatInput from '@/components/chat/ChatInput';
import { useChatStore } from '@/stores/chatStore';
import { streamChat } from '@/lib/api';
import { useCallback, useRef } from 'react';
import type { Message, SSEEvent } from '@/types/chat';

const MASCOT_URL = 'http://127.0.0.1:8765/static/mascot.png';

export default function ChatPage() {
  const { conversations, activeId, isStreaming, setStreaming, temperature, addMessage, updateMessage, newConversation } = useChatStore();

  const conv = conversations.find((c) => c.id === activeId);
  const startTimeRef = useRef<number>(0);

  const handleSend = useCallback(
    async (text: string, attachments: Array<{ name: string; data: string; isImage: boolean }>) => {
      if (isStreaming) return;
      if (!text && !attachments.length) return;

      const store = useChatStore.getState();
      if (!store.activeId) {
        store.newConversation();
      }
      const convId = store.activeId || useChatStore.getState().activeId!;
      const conv = useChatStore.getState().conversations.find((c) => c.id === convId);
      if (!conv) return;

      // Add user message
      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: text + (attachments.length ? `\n\n[附件: ${attachments.map((a) => a.name).join(', ')}]` : ''),
        timestamp: Date.now(),
        attachments: attachments.map((a) => ({ ...a, type: a.isImage ? 'image' : 'file' })),
      };
      addMessage(convId, userMsg);

      // Update conversation title if first message
      if (conv.messages.filter((m) => m.role === 'user').length === 0) {
        useChatStore.setState((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId ? { ...c, title: text.slice(0, 30) } : c,
          ),
        }));
      }

      // Add assistant placeholder
      const assistantId = `a-${Date.now()}`;
      const assistantMsg: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        reasoning: '',
        toolCalls: [],
      };
      addMessage(convId, assistantMsg);
      setStreaming(true);
      startTimeRef.current = Date.now();

      try {
        // Build message history
        const updatedConv = useChatStore.getState().conversations.find((c) => c.id === convId)!;
        const histMessages = updatedConv.messages
          .filter((m) => m.id !== assistantId)
          .map((m) => {
            if (m.attachments?.some((a) => a.isImage)) {
              const content: Array<{ type: string; text?: string; image_url?: { url: string } }> = [
                { type: 'text', text: m.content },
              ];
              m.attachments.filter((a) => a.isImage).forEach((a) => {
                content.push({ type: 'image_url', image_url: { url: a.data } });
              });
              return { role: m.role, content };
            }
            return { role: m.role, content: m.content };
          });

        // Stream
        for await (const raw of streamChat(histMessages, temperature)) {
          const evt = raw as SSEEvent;
          const current = useChatStore.getState().conversations.find((c) => c.id === convId)?.messages.find((m) => m.id === assistantId);
          if (!current) break;

          if (evt.type === 'reasoning') {
            updateMessage(convId, assistantId, { reasoning: (current.reasoning || '') + (evt.content || '') });
          } else if (evt.type === 'text') {
            updateMessage(convId, assistantId, { content: (current.content || '') + (evt.content || '') });
          } else if (evt.type === 'tool') {
            const newCall = { id: `tc-${Date.now()}`, name: evt.name || '', args: evt.args || {}, result: null };
            updateMessage(convId, assistantId, {
              toolCalls: [...(current.toolCalls || []), newCall],
            });
          } else if (evt.type === 'tool_result') {
            const calls = [...(current.toolCalls || [])];
            const last = calls[calls.length - 1];
            if (last) last.result = evt.result || '';
            updateMessage(convId, assistantId, { toolCalls: calls });
          } else if (evt.type === 'done') {
            updateMessage(convId, assistantId, { model: evt.model });
          } else if (evt.type === 'error') {
            updateMessage(convId, assistantId, {
              content: (current.content || '') + `\n\nError: ${evt.message}`,
            });
          }
        }
      } catch (e) {
        const current = useChatStore.getState().conversations.find((c) => c.id === convId)?.messages.find((m) => m.id === assistantId);
        updateMessage(convId, assistantId, {
          content: (current?.content || '') + `\n\nNetwork error: ${(e as Error).message}`,
        });
      } finally {
        setStreaming(false);
      }
    },
    [isStreaming, temperature, addMessage, updateMessage, setStreaming],
  );

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-hidden">
          <MessageList messages={conv?.messages || []} />
        </div>
        <ChatInput
          onSend={(text, attachments, temp) => handleSend(text, attachments)}
          disabled={isStreaming}
        />
      </div>
    </AppShell>
  );
}
