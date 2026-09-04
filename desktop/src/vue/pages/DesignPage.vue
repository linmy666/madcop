<script setup lang="ts">
/**
 * DesignPage — 原型工坊 (Prototype Workshop), hybrid PM tool.
 *
 * Left rail:  generate-from-prompt + prototype file list
 * Center:     live preview (iframe, phone frame)
 * Right:      code editor for manual fixes
 *
 * The hybrid contract: natural language generates the first cut;
 * the code editor is the hallucination antidote — PMs hand-tweak
 * what the model got wrong, save hot, preview re-renders instantly.
 * For bigger revisions, copy the file path into the main chat and
 * ask the agent to edit it (same file, same preview).
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getApiUrl } from '../api/client'
import { useUIStore } from '../stores/uiStore'

const uiStore = useUIStore()

interface ProtoFile { name: string; size: number; mtime: number }

// ── state ──────────────────────────────────────────────────────────────
const files = ref<ProtoFile[]>([])
const selected = ref('')
const content = ref('')
const savedContent = ref('')
const loadingList = ref(false)
const loadingFile = ref(false)
const saving = ref(false)
const generating = ref(false)
const prompt = ref('')
const genError = ref('')
const rightTab = ref<'code' | 'howto'>('code')
const previewBust = ref(0)

const PRESET_PROMPTS = [
  { label: '登录页', prompt: '一个简洁的移动端登录页：手机号+验证码输入、登录按钮、第三方登录图标行、用户协议勾选。含验证码倒计时交互和输入校验错误示例。' },
  { label: '订单列表', prompt: '移动端订单列表页：顶部状态 tab（全部/待支付/已完成），订单卡片（商家名、商品摘要、金额、操作按钮），含空态和加载占位。' },
  { label: '表单页', prompt: '移动端收货地址编辑表单：姓名/手机/省市区选择器/详细地址/默认地址开关，保存按钮。含必填校验错误和保存成功 toast。' },
  { label: '数据看板', prompt: '移动端数据看板：4 张指标卡（今日订单/收入/活跃/转化率）、一个 7 日趋势图（纯 CSS 柱状）、一个排行列表。' },
]

const previewUrl = computed(() =>
  selected.value
    ? `${getApiUrl(`/api/v4/design/preview?name=${encodeURIComponent(selected.value)}`)}&t=${previewBust.value}`
    : '')

// ── point-to-edit (v0 Design Mode / Figma Make parity) ────────────────
const selection = ref<{ selector: string; html: string; text: string } | null>(null)
const editInstruction = ref('')

function onSelectMessage(e: MessageEvent) {
  const d = e.data
  if (!d || d.type !== 'madcop-select') return
  selection.value = { selector: String(d.selector || ''), html: String(d.html || ''), text: String(d.text || '') }
  editInstruction.value = ''
}

function composePointEditPrompt(): string {
  const sel = selection.value
  if (!sel) return ''
  const req = editInstruction.value.trim() || '按用户接下来的描述修改'
  return (
    `请修改原型文件 ${selected.value} 中选中的元素。\n` +
    `选择器：${sel.selector}\n` +
    `元素 HTML：\n${sel.html}\n` +
    `修改要求：${req}\n` +
    '请用 edit_file 精准修改该元素，不要改动文件其他部分。'
  )
}

async function copyPointEdit() {
  const promptText = composePointEditPrompt()
  if (!promptText) return
  try {
    await navigator.clipboard.writeText(promptText)
    uiStore.addToast({ type: 'success', message: '点选修改提示词已复制——粘贴到主会话发送即可' })
  } catch {
    uiStore.addToast({ type: 'error', message: '复制失败，请手动选择文本' })
  }
}

function clearSelection() {
  selection.value = null
  editInstruction.value = ''
}

const isDirty = computed(() => content.value !== savedContent.value)
const canSave = computed(() => isDirty.value && !!selected.value && !saving.value)

const sizeLabel = (b: number) => b >= 1024 ? `${(b / 1024).toFixed(1)} KB` : `${b} B`
const timeLabel = (ts: number) => {
  const d = new Date(ts * 1000)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// ── data ───────────────────────────────────────────────────────────────
async function fetchFiles(selectFirst = false) {
  loadingList.value = true
  try {
    const res = await fetch(getApiUrl('/api/v4/design/files'))
    const data = await res.json()
    files.value = data.files || []
    if (selectFirst && files.value.length && !selected.value) {
      await selectFile(files.value[0].name)
    }
  } catch {
    uiStore.addToast({ type: 'error', message: '原型列表加载失败' })
  } finally {
    loadingList.value = false
  }
}

async function selectFile(name: string) {
  if (isDirty.value && !confirm('当前有未保存的修改，切换会丢失。继续？')) return
  loadingFile.value = true
  try {
    const res = await fetch(getApiUrl(`/api/v4/design/file?name=${encodeURIComponent(name)}`))
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.detail || '读取失败')
    selected.value = data.name
    content.value = data.content
    savedContent.value = data.content
    previewBust.value = Date.now()
    showVersions.value = false
    void fetchVersions()
  } catch (e: any) {
    uiStore.addToast({ type: 'error', message: e?.message || '读取失败' })
  } finally {
    loadingFile.value = false
  }
}

async function saveFile() {
  if (!canSave.value) return
  saving.value = true
  try {
    const res = await fetch(getApiUrl('/api/v4/design/file'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: selected.value, content: content.value }),
    })
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    savedContent.value = content.value
    previewBust.value = Date.now()
    uiStore.addToast({ type: 'success', message: '已保存，预览已更新' })
    void fetchFiles()
  } catch (e: any) {
    uiStore.addToast({ type: 'error', message: e?.message || '保存失败' })
  } finally {
    saving.value = false
  }
}

async function generate() {
  const p = prompt.value.trim()
  if (!p || generating.value) return
  generating.value = true
  genError.value = ''
  try {
    const res = await fetch(getApiUrl('/api/v4/design/generate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: p }),
    })
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    await fetchFiles()
    await selectFile(data.name)
    prompt.value = ''
    uiStore.addToast({
      type: 'success',
      message: `生成完成（${data.elapsed_s}s，${sizeLabel(data.bytes)}）——可在右侧代码里修正细节`,
    })
  } catch (e: any) {
    genError.value = e?.message || '生成失败'
  } finally {
    generating.value = false
  }
}

async function deleteFile(name: string) {
  if (!confirm(`删除原型 ${name}？此操作不可恢复。`)) return
  try {
    const res = await fetch(
      getApiUrl(`/api/v4/design/file?name=${encodeURIComponent(name)}`),
      { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    if (selected.value === name) {
      selected.value = ''
      content.value = ''
      savedContent.value = ''
    }
    await fetchFiles()
  } catch (e: any) {
    uiStore.addToast({ type: 'error', message: e?.message || '删除失败' })
  }
}

function onEditorKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault()
    void saveFile()
  }
  if (e.key === 'Tab') {
    e.preventDefault()
    const ta = e.target as HTMLTextAreaElement
    const { selectionStart: a, selectionEnd: b, value } = ta
    ta.value = value.slice(0, a) + '  ' + value.slice(b)
    ta.selectionStart = ta.selectionEnd = a + 2
    content.value = ta.value
  }
}

function copyPath() {
  void navigator.clipboard?.writeText(selected.value || '')
}

// ── version history ────────────────────────────────────────────────────
interface ProtoVersion { ts: number; size: number; version_id: string }
const versions = ref<ProtoVersion[]>([])
const showVersions = ref(false)
const loadingVersions = ref(false)

const vLabel = (ts: number) => {
  const d = new Date(ts)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

async function fetchVersions() {
  if (!selected.value) return
  loadingVersions.value = true
  try {
    const res = await fetch(getApiUrl(`/api/v4/design/versions?name=${encodeURIComponent(selected.value)}`))
    const data = await res.json()
    versions.value = data.versions || []
  } catch {
    versions.value = []
  } finally {
    loadingVersions.value = false
  }
}

function toggleVersions() {
  showVersions.value = !showVersions.value
  if (showVersions.value) void fetchVersions()
}

async function loadVersion(versionId: string) {
  if (!selected.value) return
  if (isDirty.value && !confirm('加载旧版本会丢弃未保存的修改。继续？')) return
  try {
    const res = await fetch(getApiUrl(`/api/v4/design/version?name=${encodeURIComponent(selected.value)}&version_id=${versionId}`))
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.detail || '读取失败')
    content.value = data.content
    savedContent.value = data.content
    previewBust.value = Date.now()
    showVersions.value = false
    uiStore.addToast({ type: 'success', message: '已载入历史版本——点保存即可回滚到该版本' })
  } catch (e: any) {
    uiStore.addToast({ type: 'error', message: e?.message || '载入失败' })
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  window.addEventListener('message', onSelectMessage)
  void fetchFiles(true)
  // Light poll so agent-written prototypes (from the main chat) appear.
  pollTimer = setInterval(() => {
    if (!generating.value && !isDirty.value) void fetchFiles()
  }, 8000)
})
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  window.removeEventListener('message', onSelectMessage)
})
</script>

<template>
  <div class="proto-ws">
    <!-- Left rail: generate + file list -->
    <aside class="pw-rail">
      <div class="pw-rail__sec">
        <div class="pw-rail__title">生成原型</div>
        <textarea
          v-model="prompt"
          class="pw-prompt"
          rows="3"
          :disabled="generating"
          placeholder="描述你要的原型，如：外卖下单页，含地址卡、商品清单、备注和提交按钮…"
          @keydown.enter.exact.prevent="generate"
        ></textarea>
        <div class="pw-presets">
          <button
            v-for="preset in PRESET_PROMPTS"
            :key="preset.label"
            type="button"
            class="pw-preset"
            :disabled="generating"
            @click="prompt = preset.prompt"
          >{{ preset.label }}</button>
        </div>
        <button
          type="button"
          class="pw-generate"
          :disabled="generating || !prompt.trim()"
          @click="generate"
        >
          <span v-if="generating" class="material-symbols-outlined animate-spin text-[15px]">progress_activity</span>
          <span v-else class="material-symbols-outlined text-[15px]">auto_awesome</span>
          {{ generating ? '生成中…（约 1-2 分钟）' : '生成原型' }}
        </button>
        <p v-if="genError" class="pw-generr">{{ genError }}</p>
      </div>

      <div class="pw-rail__sec pw-rail__files">
        <div class="pw-rail__title">我的原型 <span class="pw-count">{{ files.length }}</span></div>
        <div v-if="loadingList && !files.length" class="pw-empty">加载中…</div>
        <div v-else-if="!files.length" class="pw-empty">还没有原型——左侧描述一个试试</div>
        <button
          v-for="f in files"
          :key="f.name"
          type="button"
          class="pw-file"
          :class="{ 'pw-file--active': f.name === selected }"
          @click="selectFile(f.name)"
        >
          <span class="material-symbols-outlined pw-file__icon">html</span>
          <span class="pw-file__meta">
            <span class="pw-file__name">{{ f.name }}</span>
            <span class="pw-file__sub">{{ sizeLabel(f.size) }} · {{ timeLabel(f.mtime) }}</span>
          </span>
          <span
            class="material-symbols-outlined pw-file__del"
            title="删除"
            @click.stop="deleteFile(f.name)"
          >delete</span>
        </button>
      </div>
    </aside>

    <!-- Main: preview + editor -->
    <main class="pw-main">
      <div v-if="!selected" class="pw-noselect">
        <span class="material-symbols-outlined pw-noselect__icon">design_services</span>
        <p>选择或生成一个原型开始</p>
        <p class="pw-noselect__sub">自然语言出初稿 → 代码编辑修正细节 → 保存即所见</p>
      </div>
      <template v-else>
        <div class="pw-toolbar">
          <span class="pw-toolbar__name">{{ selected }}</span>
          <span v-if="isDirty" class="pw-toolbar__dirty">未保存</span>
          <span class="pw-toolbar__spacer"></span>
          <button
            type="button"
            class="pw-toolbar__tab"
            data-testid="history-btn"
            @click="toggleVersions"
          >
            <span class="material-symbols-outlined text-[13px] align-middle">history</span>
            历史{{ versions.length ? ` (${versions.length})` : '' }}
          </button>
          <div v-if="showVersions" class="pw-versions">
            <div v-if="loadingVersions" class="pw-versions__empty">加载中…</div>
            <div v-else-if="!versions.length" class="pw-versions__empty">暂无历史版本——每次保存都会自动留一个快照</div>
            <button
              v-for="v in versions"
              :key="v.version_id"
              type="button"
              class="pw-versions__row"
              @click="loadVersion(v.version_id)"
            >
              <span class="material-symbols-outlined text-[14px]">restore</span>
              <span class="pw-versions__time">{{ vLabel(v.ts) }}</span>
              <span class="pw-versions__size">{{ sizeLabel(v.size) }}</span>
            </button>
          </div>
          <button
            type="button"
            class="pw-toolbar__tab"
            :class="{ 'pw-toolbar__tab--on': rightTab === 'code' }"
            @click="rightTab = rightTab === 'code' ? 'howto' : 'code'"
          >{{ rightTab === 'code' ? '切到说明' : '切到代码' }}</button>
          <button
            type="button"
            class="pw-save"
            :disabled="!canSave"
            title="保存并刷新预览（⌘S）"
            @click="saveFile"
          >
            <span v-if="saving" class="material-symbols-outlined animate-spin text-[14px]">progress_activity</span>
            <span v-else class="material-symbols-outlined text-[14px]">save</span>
            保存
          </button>
        </div>

        <div class="pw-split" :class="{ 'pw-split--editor': rightTab === 'code' }">
          <!-- Preview: phone frame -->
          <div class="pw-preview-pane">
            <iframe
              :key="previewBust"
              :src="previewUrl"
              class="pw-frame"
              title="原型预览"
              sandbox="allow-scripts allow-forms allow-modals"
            ></iframe>
            <!-- Point-to-edit bar: click an element in the preview to
                 select it; compose a pinpoint edit prompt anchored to the
                 element's exact selector (v0 Design Mode parity). -->
            <div v-if="selection" class="pw-selectbar" data-testid="point-edit-bar">
              <div class="pw-selectbar__sel">
                <span class="material-symbols-outlined text-[13px]">ads_click</span>
                <code class="pw-selectbar__selector">{{ selection.selector }}</code>
                <button type="button" class="pw-selectbar__close" aria-label="清除选择" @click="clearSelection">
                  <span class="material-symbols-outlined text-[14px]">close</span>
                </button>
              </div>
              <input
                v-model="editInstruction"
                class="pw-selectbar__input"
                placeholder="想让它怎么改？如：文字改成「立即下单」并加大内边距"
                @keydown.enter="copyPointEdit"
              />
              <button type="button" class="pw-selectbar__copy" @click="copyPointEdit">
                <span class="material-symbols-outlined text-[14px]">content_copy</span>
                复制给 MadCop
              </button>
            </div>
          </div>
          <!-- Editor pane -->
          <div class="pw-editor-pane">
            <textarea
              v-if="rightTab === 'code'"
              v-model="content"
              class="pw-editor"
              spellcheck="false"
              wrap="off"
              @keydown="onEditorKeydown"
            ></textarea>
            <div v-else class="pw-howto">
              <h4>混合编辑工作流</h4>
              <ol>
                <li><b>自然语言出初稿</b>：左侧描述需求，生成可交互原型。</li>
                <li><b>手动修正幻觉</b>：模型写错的文案、布局、逻辑，直接在代码页改，⌘S 保存即时生效。</li>
                <li><b>大改动交给 agent</b>：把下面的文件路径复制到主会话，让 MadCop 用工具直接修改这个文件——改完这里会自动出现。</li>
              </ol>
              <div class="pw-path">
                <code>{{ selected }}</code>
                <button
                  type="button"
                  class="pw-path__copy"
                  @click="copyPath"
                >复制路径</button>
              </div>
              <p class="pw-howto__tip">提示：主会话里说"把 {{ selected }} 的按钮改成主色、加一个地址联想"，MadCop 会用 edit_file 精准修改。</p>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.proto-ws {
  display: flex;
  height: 100%;
  min-height: 0;
  width: 100%;
  background: var(--color-surface, #fff);
}
/* ── left rail ── */
.pw-rail {
  width: 264px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-border, #e5e5e5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.pw-rail__sec {
  padding: 14px;
  border-bottom: 1px solid var(--color-border, #ececec);
}
.pw-rail__files {
  flex: 1;
  overflow-y: auto;
  border-bottom: 0;
}
.pw-rail__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary, #555);
  margin-bottom: 8px;
}
.pw-count {
  color: var(--color-text-tertiary, #999);
  font-weight: 400;
}
.pw-prompt {
  width: 100%;
  resize: vertical;
  padding: 8px 10px;
  border: 1px solid var(--color-border, #ddd);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-primary, #111);
  background: var(--color-surface, #fff);
  outline: none;
  font-family: inherit;
}
.pw-prompt:focus { border-color: var(--color-brand, #4f46e5); }
.pw-presets { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.pw-preset {
  padding: 3px 10px;
  font-size: 11px;
  border-radius: 999px;
  border: 1px solid var(--color-border, #ddd);
  background: transparent;
  color: var(--color-text-secondary, #555);
  cursor: pointer;
}
.pw-preset:hover { border-color: var(--color-brand, #4f46e5); color: var(--color-brand, #4f46e5); }
.pw-generate {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 0;
  border-radius: 8px;
  border: 0;
  background: var(--color-primary, #4f46e5);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.pw-generate:disabled { opacity: 0.5; cursor: default; }
.pw-generr { margin-top: 8px; font-size: 11px; color: var(--color-error, #dc2626); }
.pw-empty { font-size: 12px; color: var(--color-text-tertiary, #999); padding: 8px 0; }
.pw-file {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border-radius: 8px;
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.pw-file:hover { background: var(--color-surface-hover, #f3f3f3); }
.pw-file--active { background: var(--color-surface-container, #ececf1); }
.pw-file__icon { font-size: 17px; color: var(--color-text-tertiary, #999); flex-shrink: 0; }
.pw-file__meta { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.pw-file__name {
  font-size: 12px;
  color: var(--color-text-primary, #111);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pw-file__sub { font-size: 10px; color: var(--color-text-tertiary, #999); }
.pw-file__del {
  font-size: 14px;
  color: var(--color-text-tertiary, #bbb);
  opacity: 0;
  border-radius: 4px;
  padding: 2px;
}
.pw-file:hover .pw-file__del { opacity: 1; }
.pw-file__del:hover { color: var(--color-error, #dc2626); background: rgba(220,38,38,0.08); }

/* ── main ── */
.pw-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.pw-noselect {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--color-text-secondary, #555);
  font-size: 14px;
}
.pw-noselect__icon { font-size: 44px; color: var(--color-text-tertiary, #bbb); }
.pw-noselect__sub { font-size: 12px; color: var(--color-text-tertiary, #999); }

.pw-toolbar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border, #ececec);
  flex-shrink: 0;
}
.pw-toolbar__name {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px;
  color: var(--color-text-primary, #111);
}
.pw-toolbar__dirty {
  font-size: 11px;
  color: #b45309;
  background: rgba(180,83,9,0.1);
  padding: 1px 8px;
  border-radius: 999px;
}
.pw-toolbar__spacer { flex: 1; }
.pw-toolbar__tab {
  font-size: 11px;
  border: 1px solid var(--color-border, #ddd);
  background: transparent;
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  color: var(--color-text-secondary, #555);
}
.pw-toolbar__tab--on { border-color: var(--color-brand, #4f46e5); color: var(--color-brand, #4f46e5); }
.pw-save {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 14px;
  border-radius: 7px;
  border: 0;
  background: var(--color-primary, #4f46e5);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.pw-save:disabled { opacity: 0.45; cursor: default; }

.pw-split {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}
/* Preview: phone-width frame centered on a quiet bg */
.pw-preview-pane {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 20px;
  overflow: auto;
  background: var(--color-surface-container-lowest, #fafafa);
}
.pw-frame {
  width: 390px;
  height: 100%;
  min-height: 480px;
  border: 1px solid var(--color-border, #e0e0e0);
  border-radius: 18px;
  background: #fff;
}
/* Editor pane: slides in when the code tab is on */
.pw-editor-pane {
  width: 0;
  flex-shrink: 0;
  overflow: hidden;
  border-left: 1px solid var(--color-border, #ececec);
  transition: width 160ms ease-out;
  display: flex;
  flex-direction: column;
}
.pw-split--editor .pw-editor-pane { width: 46%; }
.pw-editor {
  flex: 1;
  width: 100%;
  padding: 12px;
  border: 0;
  outline: none;
  resize: none;
  background: var(--color-surface-container-lowest, #fafafa);
  color: var(--color-text-primary, #111);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.6;
  tab-size: 2;
  white-space: pre;
}
.pw-howto {
  flex: 1;
  padding: 16px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--color-text-secondary, #555);
  overflow: auto;
}
.pw-howto h4 { font-size: 13px; color: var(--color-text-primary, #111); margin: 0 0 8px; }
.pw-howto ol { padding-left: 18px; margin: 0 0 12px; }
.pw-howto li { margin-bottom: 6px; }
.pw-path {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--color-border, #e0e0e0);
  border-radius: 8px;
  background: var(--color-surface-container-low, #f7f7f8);
}
.pw-path code { flex: 1; font-size: 11px; color: var(--color-text-primary, #111); word-break: break-all; }
.pw-path__copy {
  font-size: 11px;
  border: 1px solid var(--color-border, #ddd);
  background: #fff;
  border-radius: 6px;
  padding: 2px 8px;
  cursor: pointer;
  color: var(--color-text-secondary, #555);
}
.pw-howto__tip { margin-top: 10px; font-size: 11px; color: var(--color-text-tertiary, #999); }

.pw-versions {
  position: absolute;
  top: 44px;
  right: 60px;
  z-index: 30;
  min-width: 230px;
  max-height: 300px;
  overflow-y: auto;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e0e0e0);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.1);
  padding: 4px;
}
.pw-versions__row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: var(--color-text-secondary, #555);
  text-align: left;
}
.pw-versions__row:hover { background: var(--color-surface-hover, #f3f3f3); }
.pw-versions__time { flex: 1; font-variant-numeric: tabular-nums; }
.pw-versions__size { color: var(--color-text-tertiary, #999); font-size: 11px; }
.pw-versions__empty { padding: 10px; font-size: 12px; color: var(--color-text-tertiary, #999); }

.pw-selectbar {
  position: absolute;
  left: 20px;
  right: 20px;
  bottom: 16px;
  z-index: 40;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--color-brand, #4f46e5);
  border-radius: 12px;
  background: var(--color-surface, #fff);
  box-shadow: 0 8px 28px rgba(0,0,0,0.14);
}
.pw-selectbar__sel { display: flex; align-items: center; gap: 6px; min-width: 0; }
.pw-selectbar__selector {
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 11px;
  color: var(--color-brand, #4f46e5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pw-selectbar__close {
  border: 0; background: transparent; cursor: pointer;
  color: var(--color-text-tertiary, #999); border-radius: 4px; padding: 1px;
}
.pw-selectbar__input {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--color-border, #ddd);
  border-radius: 8px;
  font-size: 12px;
  outline: none;
  color: var(--color-text-primary, #111);
  background: var(--color-surface, #fff);
  font-family: inherit;
}
.pw-selectbar__input:focus { border-color: var(--color-brand, #4f46e5); }
.pw-selectbar__copy {
  align-self: flex-end;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: 7px;
  border: 0;
  background: var(--color-primary, #4f46e5);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

@media (max-width: 900px) {
  .pw-split--editor .pw-editor-pane { width: 60%; }
  .pw-preview-pane { padding: 10px; }
}
</style>
