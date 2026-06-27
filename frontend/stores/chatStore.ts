'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Conversation, Message } from '@/types/chat';

interface ChatState {
  conversations: Conversation[];
  activeId: string | null;
  isStreaming: boolean;
  temperature: number;
  theme: 'dark' | 'light';
  sidebarOpen: boolean;

  // Actions
  newConversation: () => void;
  deleteConversation: (id: string) => void;
  setActive: (id: string) => void;
  addMessage: (convId: string, msg: Message) => void;
  updateMessage: (convId: string, msgId: string, patch: Partial<Message>) => void;
  setStreaming: (v: boolean) => void;
  setTemperature: (t: number) => void;
  toggleTheme: () => void;
  toggleSidebar: () => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeId: null,
      isStreaming: false,
      temperature: 0.7,
      theme: 'dark',
      sidebarOpen: true,

      newConversation: () => {
        const id = Date.now().toString();
        const conv: Conversation = {
          id,
          title: '新对话',
          messages: [],
          createdAt: Date.now(),
        };
        set((s) => ({
          conversations: [...s.conversations, conv],
          activeId: id,
        }));
      },

      deleteConversation: (id) => {
        set((s) => {
          const conversations = s.conversations.filter((c) => c.id !== id);
          const activeId =
            s.activeId === id
              ? conversations.length > 0
                ? conversations[conversations.length - 1].id
                : null
              : s.activeId;
          return { conversations, activeId };
        });
      },

      setActive: (id) => set({ activeId: id }),

      addMessage: (convId, msg) => {
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId
              ? { ...c, messages: [...c.messages, msg] }
              : c,
          ),
        }));
      },

      updateMessage: (convId, msgId, patch) => {
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === msgId ? { ...m, ...patch } : m,
                  ),
                }
              : c,
          ),
        }));
      },

      setStreaming: (v) => set({ isStreaming: v }),
      setTemperature: (t) => set({ temperature: t }),
      toggleTheme: () =>
        set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
      toggleSidebar: () =>
        set((s) => ({ sidebarOpen: !s.sidebarOpen })),
    }),
    {
      name: 'madcop-chat',
      partialize: (s) => ({
        conversations: s.conversations.slice(-50),
        temperature: s.temperature,
        theme: s.theme,
      }),
    },
  ),
);

export function getActiveConversation(): Conversation | null {
  const s = useChatStore.getState();
  if (!s.activeId) return null;
  return s.conversations.find((c) => c.id === s.activeId) || null;
}
