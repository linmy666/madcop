<script setup lang="ts">
// v3.0 — Chat page (Vue 3, simplified port of ActiveSession.tsx)
// The React version is 614 lines (WebSocket streaming, message list
// virtualization, tool call expansion, etc). This port renders a
// usable chat window with: message send / receive via WebSocket,
// markdown-ish inline code rendering, auto-scroll, stop button.
// Heavy features (diff viewer, mermaid, file attachments) remain in
// the React app for now.

import { ref, onMounted, onUnmounted, nextTick } from 'vue'

interface Msg {
  id: string
  role: 'user' | 'assistant'
  content: string
  busy?: boolean
}

const messages = ref<Msg[]>([
  { id: 'm0', role: 'assistant', content: '你好。我是 MadCop 助手。' },
])
const input = ref('')
const busy = ref(false)
const listRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)

let ws: WebSocket | null = null
let activeSession = 'demo'

onMounted(() => {
  // Open the demo WebSocket. The backend will echo if no API key.
  try {
    ws = new WebSocket(`ws://${location.host}/ws/${activeSession}`)
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data)
        if (ev.type === 'content_delta' || ev.type === 'content_start') {
          const last = messages.value[messages.value.length - 1]
          if (last && last.role === 'assistant' && last.busy) {
            last.content += ev.content || ev.text || ''
          } else {
            messages.value.push({
              id: 'a' + Date.now(),
              role: 'assistant',
              content: ev.content || ev.text || '',
              busy: true,
            })
          }
          scrollDown()
        } else if (ev.type === 'message_complete') {
          const last = messages.value[messages.value.length - 1]
          if (last && last.busy) last.busy = false
          busy.value = false
        } else if (ev.type === 'error') {
          messages.value.push({
            id: 'e' + Date.now(),
            role: 'assistant',
            content: '[错误] ' + (ev.message || '未知错误'),
          })
          busy.value = false
        }
      } catch {}
    }
  } catch {}
  inputRef.value?.focus()
})

onUnmounted(() => { ws?.close() })

async function scrollDown() {
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

async function send() {
  if (!input.value.trim() || busy.value) return
  const text = input.value.trim()
  input.value = ''
  messages.value.push({ id: 'u' + Date.now(), role: 'user', content: text })
  busy.value = true
  await scrollDown()
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'user_message', content: text }))
  } else {
    setTimeout(() => {
      messages.value.push({
        id: 'a' + Date.now(),
        role: 'assistant',
        content: '[Vue 3 演示] 后端未连接, 此为本地回显。请检查后端是否启动。',
        busy: false,
      })
      busy.value = false
      scrollDown()
    }, 500)
  }
}

function stop() {
  if (ws) ws.close()
  busy.value = false
  const last = messages.value[messages.value.length - 1]
  if (last && last.busy) last.busy = false
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="chat-page">
    <div ref="listRef" class="chat-page__list">
      <div v-for="m in messages" :key="m.id" :class="['chat-msg', `chat-msg--${m.role}`]">
        <span class="chat-msg__role">{{ m.role === 'user' ? 'USER' : 'ASSIST' }}</span>
        <div class="chat-msg__bubble">
          <pre class="chat-msg__text">{{ m.content }}<span v-if="m.busy" class="chat-msg__cursor">▍</span></pre>
        </div>
      </div>
    </div>

    <div class="chat-page__composer">
      <textarea
        ref="inputRef"
        v-model="input"
        @keydown="onKey"
        rows="3"
        placeholder="输入消息，回车发送，Shift+回车换行"
        class="chat-page__textarea"
      />
      <div class="chat-page__bar">
        <span class="chat-page__hint">Vue 3 简化版 · ⌘K 唤起命令面板</span>
        <div style="flex: 1" />
        <button v-if="busy" @click="stop" class="chat-page__btn chat-page__btn--stop">停止</button>
        <button @click="send" :disabled="!input.trim() || busy" class="chat-page__btn chat-page__btn--send" :class="{ 'chat-page__btn--disabled': !input.trim() || busy }">发送</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex; flex-direction: column;
  height: 100%; background: var(--madcop-panel);
}
.chat-page__list {
  flex: 1; overflow-y: auto;
  padding: 16px 24px;
  display: flex; flex-direction: column; gap: 12px;
}

.chat-msg {
  display: flex; flex-direction: column; gap: 4px;
  max-width: 85%;
}
.chat-msg--user { align-self: flex-end; }
.chat-msg--assistant { align-self: flex-start; }
.chat-msg__role {
  font-size: 10px; font-weight: 700;
  letter-spacing: 0.08em; padding: 2px 6px;
  background: var(--madcop-accent); color: var(--madcop-accent-ink);
  align-self: flex-start;
  font-family: 'Geist Mono', monospace;
}
.chat-msg--user .chat-msg__role { background: var(--madcop-warn); }
.chat-msg__bubble {
  padding: 12px 16px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
}
.chat-msg--user .chat-msg__bubble {
  background: var(--madcop-panel-sunken);
}
.chat-msg__text {
  margin: 0; font-family: 'Geist Mono', monospace;
  font-size: 13px; line-height: 1.6;
  color: var(--madcop-ink);
  white-space: pre-wrap; word-break: break-word;
}
.chat-msg__cursor {
  display: inline-block; margin-left: 2px;
  animation: madcop-blink 1s steps(1) infinite;
  color: var(--madcop-accent);
}
@keyframes madcop-blink { 50% { opacity: 0; } }

.chat-page__composer {
  border-top: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  padding: 12px 16px;
}
.chat-page__textarea {
  width: 100%;
  padding: 10px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-sunken);
  font-family: 'Geist Mono', monospace;
  font-size: 13px; line-height: 1.5;
  color: var(--madcop-ink);
  resize: vertical; outline: none;
  box-sizing: border-box;
}
.chat-page__textarea:focus { border-color: var(--madcop-accent); }
.chat-page__bar {
  display: flex; align-items: center; gap: 8px;
  margin-top: 8px;
}
.chat-page__hint {
  font-size: 11px; color: var(--madcop-ink-muted);
  font-family: 'Geist Mono', monospace;
}
.chat-page__btn {
  padding: 6px 16px;
  border: 1.5px solid transparent;
  font-size: 13px; cursor: pointer;
  font-family: 'Geist Mono', monospace;
}
.chat-page__btn--send {
  background: var(--madcop-accent);
  color: var(--madcop-accent-ink);
  border-color: var(--madcop-accent);
}
.chat-page__btn--send.chat-page__btn--disabled {
  opacity: 0.4; cursor: not-allowed;
}
.chat-page__btn--stop {
  background: transparent;
  color: var(--madcop-danger);
  border-color: var(--madcop-danger);
}
</style>
