<script setup lang="ts">
// v3.0 — H5ConnectionView (Vue 3)
// Direct translation — same Tailwind classes, same form layout.
import { ref } from 'vue'
import Input from '../shared/Input.vue'
import Button from '../shared/Button.vue'

const props = defineProps<{
  initialServerUrl?: string | null
  error?: string | null
}>()

const emit = defineEmits<{ (e: 'connected'): void }>()

const serverUrl = ref(props.initialServerUrl ?? '')
const token = ref('')
const error = ref(props.error ?? '')
const submitting = ref(false)

async function handleSubmit(e: Event) {
  e.preventDefault()
  submitting.value = true
  error.value = ''
  try {
    // Call the API to verify the H5 connection
    const r = await fetch('/api/h5-access', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serverUrl: serverUrl.value, token: token.value }),
    })
    if (!r.ok) throw new Error('连接失败')
    emit('connected')
  } catch (e: any) {
    error.value = e?.message || '无法连接到 H5 服务器'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="h-screen flex items-center justify-center bg-[var(--color-surface)] px-6">
    <section class="w-full max-w-md rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-6 shadow-md">
      <div class="mb-5">
        <h1 class="text-lg font-semibold text-[var(--color-text-primary)]">连接 H5 远程访问</h1>
        <p class="mt-2 text-sm text-[var(--color-text-secondary)]">输入桌面端提供的服务器 URL 和 H5 访问令牌。</p>
      </div>
      <form class="space-y-4" @submit="handleSubmit">
        <Input
          label="服务器 URL"
          placeholder="https://chat.example.com"
          v-model="serverUrl"
          required
        />
        <Input
          label="H5 令牌"
          type="password"
          placeholder="h5_..."
          v-model="token"
          required
        />
        <div v-if="error" class="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/8 px-3 py-2 text-sm text-[var(--color-error)]">
          {{ error }}
        </div>
        <Button type="submit" size="lg" class="w-full" :loading="submitting">连接</Button>
      </form>
    </section>
  </div>
</template>
