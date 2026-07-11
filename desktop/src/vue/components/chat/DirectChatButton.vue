<script setup lang="ts">
/**
 * DirectChatButton — a completely independent "运行" button
 * that bypasses ChatInput and all store complexity.
 * Calls the backend API directly via fetch.
 */

import { ref, onMounted, onBeforeUnmount } from 'vue'

const log = ref<string[]>([])

function addLog(msg: string) {
  log.value.push(msg)
  if (log.value.length > 50) log.value.shift()
}

async function directChat() {
  const ta = document.querySelector('textarea')
  if (!ta) { addLog('❌ no textarea found'); return }
  const text = ta.value.trim()
  if (!text) { addLog('⚠️ textarea is empty'); return }
  
  addLog(`📤 sending: "${text.slice(0, 40)}..."`)
  
  try {
    const res = await fetch('http://127.0.0.1:8765/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'glm-4-plus',
        messages: [{ role: 'user', content: text }],
        temperature: 0.7,
        max_tokens: 2048,
      }),
    })
    
    if (!res.ok) {
      addLog(`❌ HTTP ${res.status}: ${res.statusText}`)
      return
    }
    
    addLog('✅ connected, reading stream...')
    
    const reader = res.body?.getReader()
    if (!reader) { addLog('❌ no reader'); return }
    
    const decoder = new TextDecoder()
    let buffer = ''
    let fullText = ''
    
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.type === 'text' && event.content) {
            fullText += event.content
            addLog(`📝 ${fullText.slice(-60)}`)
          } else if (event.type === 'done') {
            addLog(`✅ done. total chars: ${fullText.length}`)
            return
          }
        } catch {}
      }
    }
    addLog(`✅ complete: ${fullText.length} chars`)
    
  } catch (e: any) {
    addLog(`❌ error: ${e?.message || e}`)
  }
}

// Keyboard shortcut: Ctrl+Enter
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    directChat()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="direct-chat">
    <button
      @click="directChat"
      class="direct-chat__btn"
      title="Ctrl+Enter 发送"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
      </svg>
      发送
    </button>
    <div v-if="log.length > 0" class="direct-chat__log">
      <div v-for="(l, i) in log.slice(-8)" :key="i" class="direct-chat__log-line">{{ l }}</div>
    </div>
  </div>
</template>

<style scoped>
.direct-chat {
  position: fixed;
  bottom: 80px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  pointer-events: none;
}
.direct-chat__btn {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  background: #7C3AED;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(124, 58, 237, 0.4);
  transition: all 0.15s;
}
.direct-chat__btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(124, 58, 237, 0.5);
}
.direct-chat__btn:active {
  transform: translateY(0);
}
.direct-chat__log {
  pointer-events: auto;
  background: rgba(30, 30, 30, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 8px 12px;
  max-width: 360px;
  max-height: 300px;
  overflow-y: auto;
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 11px;
  line-height: 1.5;
}
.direct-chat__log-line {
  color: #e0e0e0;
  padding: 1px 0;
  word-break: break-all;
}
</style>