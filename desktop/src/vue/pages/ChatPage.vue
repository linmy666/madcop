<script setup lang="ts">
// v3.0 — ChatPage (Vue 3) — uses ChatInput + MessageList with Pinia stores
// Replaces the self-contained chat UI with the complete P0 components.

import { onMounted, computed } from 'vue'
import ChatInput from '../components/chat/ChatInput.vue'
import MessageList from '../components/chat/MessageList.vue'
import { useChatStore } from '../stores/chatStore'
import { useTabStore } from '../stores/tabs'
import { useSessionStore } from '../stores/sessionStore'
import { useSettingsStore } from '../stores/settingsStore'

const chatStore = useChatStore()
const tabStore = useTabStore()
const sessionStore = useSessionStore()
const settingsStore = useSettingsStore()

const activeSessionId = computed(() => tabStore.activeTabId)

onMounted(() => {
  // Initialize a default session if none exists
  if (!sessionStore.sessions.length) {
    void sessionStore.fetchSessions()
  }
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Message list -->
    <MessageList :session-id="activeSessionId" />

    <!-- Chat input -->
    <ChatInput :session-id="activeSessionId" />
  </div>
</template>