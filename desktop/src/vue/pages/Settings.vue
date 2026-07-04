<script setup lang="ts">
// v3.0 — Settings (Vue 3, simplified)
// The React Settings.tsx is 4,600+ lines (40+ sub-panels, drag-drop
// QR, dnd-kit, i18n, etc). We port the core 4 sections only — looks,
// model, shortcuts, about. Other settings stay in the React app.
import { ref, onMounted } from 'vue'
import { useAppearance, type Appearance } from '../composables/useAppearance'

const { appearance, setAppearance } = useAppearance()
const providers = ref<Array<{ id: string; name: string; model: string; has_key: boolean }>>([])
const activeProvider = ref<string>('')
const activeModel = ref<string>('')

onMounted(async () => {
  try {
    const r = await fetch('/api/settings')
    const s = await r.json()
    providers.value = Object.values(s.providers || {})
    activeProvider.value = s.active_provider
  } catch {}
})
</script>

<template>
  <div class="settings-page">
    <div class="settings-page__inner">
      <h1 class="settings-page__title">设置</h1>

      <!-- ── 外观 ── -->
      <section class="settings-section">
        <div class="settings-section__label">外观</div>
        <div class="settings-section__panel">
          <div class="settings-row">
            <div>
              <div class="settings-row__label">主题</div>
              <div class="settings-row__hint">亮色 / 暗色 / 牛皮纸</div>
            </div>
            <div class="settings-row__ctrl">
              <button
                v-for="a in (['light', 'dark', 'sepia'] as Appearance[])" :key="a"
                :class="['settings-pill', { 'settings-pill--active': appearance === a }]"
                @click="setAppearance(a)"
              >
                {{ a === 'light' ? '亮色' : a === 'dark' ? '暗色' : '牛皮纸' }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- ── 模型 ── -->
      <section class="settings-section">
        <div class="settings-section__label">模型</div>
        <div class="settings-section__panel">
          <div class="settings-row">
            <div>
              <div class="settings-row__label">当前供应商</div>
              <div class="settings-row__hint">点击切换激活的 provider</div>
            </div>
            <div class="settings-row__ctrl">
              <select v-model="activeProvider" class="settings-input">
                <option v-for="p in providers" :key="p.id" :value="p.id">
                  {{ p.name }}{{ p.has_key ? '' : ' (无 API key)' }}
                </option>
              </select>
            </div>
          </div>
          <div class="settings-row">
            <div>
              <div class="settings-row__label">当前模型</div>
              <div class="settings-row__hint">如 glm-5.2 / deepseek-v4-flash</div>
            </div>
            <div class="settings-row__ctrl">
              <input v-model="activeModel" type="text" class="settings-input" placeholder="glm-5.2" />
            </div>
          </div>
        </div>
      </section>

      <!-- ── 快捷键 ── -->
      <section class="settings-section">
        <div class="settings-section__label">快捷键</div>
        <div class="settings-section__panel">
          <div class="settings-row">
            <div class="settings-row__label">命令面板</div>
            <div class="settings-row__ctrl">
              <kbd class="settings-kbd">⌘K</kbd>
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-row__label">新建会话</div>
            <div class="settings-row__ctrl">
              <kbd class="settings-kbd">⌘N</kbd>
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-row__label">切换主题</div>
            <div class="settings-row__ctrl">
              <kbd class="settings-kbd">⌘⇧L</kbd>
            </div>
          </div>
        </div>
      </section>

      <!-- ── 关于 ── -->
      <section class="settings-section">
        <div class="settings-section__label">关于</div>
        <div class="settings-section__panel">
          <div class="settings-row">
            <div class="settings-row__label">版本</div>
            <div class="settings-row__ctrl">
              <span class="settings-meta">v3.0.0</span>
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-row__label">前端框架</div>
            <div class="settings-row__ctrl">
              <span class="settings-meta">Vue 3 + Pinia (迁移中)</span>
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-row__label">LLM 客户端</div>
            <div class="settings-row__ctrl">
              <span class="settings-meta">OpenAI 兼容 · 4 个 provider</span>
            </div>
          </div>
          <div class="settings-row">
            <div class="settings-row__label">可视化编辑器</div>
            <div class="settings-row__ctrl">
              <span class="settings-meta">原生 HTML5 · 0 依赖</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  width: 100%; height: 100%;
  overflow-y: auto;
  background: var(--madcop-panel);
}
.settings-page__inner {
  max-width: 720px; margin: 0 auto;
  padding: 32px 20px;
}
.settings-page__title {
  font-size: 26px; font-weight: 600;
  margin: 0 0 24px;
  letter-spacing: -0.025em;
  color: var(--madcop-ink);
}

.settings-section { margin-bottom: 32px; }
.settings-section__label {
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--madcop-ink-muted);
  margin-bottom: 8px;
}
.settings-section__panel {
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
}

.settings-row {
  display: grid; grid-template-columns: 180px 1fr;
  align-items: center; gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--madcop-line);
}
.settings-row:last-child { border-bottom: none; }
.settings-row__label { font-size: 13px; font-weight: 500; color: var(--madcop-ink); }
.settings-row__hint  { font-size: 11px; color: var(--madcop-ink-muted); margin-top: 2px; }
.settings-row__ctrl  { display: flex; align-items: center; gap: 8px; }

.settings-pill {
  padding: 6px 14px;
  background: var(--madcop-panel-raised);
  color: var(--madcop-ink-body);
  border: 1.5px solid var(--madcop-line);
  font-size: 13px; cursor: pointer;
  font-family: 'Geist Mono', monospace;
}
.settings-pill--active {
  background: var(--madcop-accent-subtle);
  color: var(--madcop-accent);
  border-color: var(--madcop-accent);
}

.settings-input {
  padding: 6px 10px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-sunken);
  font-size: 13px; color: var(--madcop-ink);
  font-family: 'Geist Mono', monospace;
  outline: none; min-width: 200px;
}
.settings-input:focus { border-color: var(--madcop-accent); }

.settings-kbd {
  display: inline-block;
  padding: 4px 8px; min-width: 28px; text-align: center;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-sunken);
  color: var(--madcop-ink-body);
  font-size: 11px; font-family: 'Geist Mono', monospace;
}

.settings-meta { color: var(--madcop-ink-muted); font-size: 12px; font-family: 'Geist Mono', monospace; }
</style>
