<script setup lang="ts">
// SkillBuilder: create/toggle/delete custom skills.
// Wired to /api/agents/skills (extras/api.py, JSON-backed CRUD + toggle).

import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

interface Skill {
  id: string
  name: string
  description: string
  triggers: string[]
  steps: any[]
  enabled: boolean
  createdAt?: number
}

const skills = ref<Skill[]>([])
const loading = ref(true)
const search = ref('')
const showBuilder = ref(false)
const draftTriggers = ref('')          // comma-separated text (simpler than array v-model)
const draft = ref<Skill>({
  id: '', name: '', description: '',
  triggers: [], steps: [], enabled: true,
})

async function load() {
  loading.value = true
  try {
    const res = await fetch(getApiUrl('/api/agents/skills'))
    if (res.ok) skills.value = await res.json()
    // Merge manual skills (~/.madcop/skills/*.md, Qoder-style with
    // category markers) so the builder shows the full library.
    const ures = await fetch(getApiUrl('/api/skills'))
    if (ures.ok) {
      const data = await ures.json()
      const manual = (data.skills || []).map((u: any) => ({
        id: `manual:${u.name}`,
        name: u.displayName || u.name,
        description: u.description || '',
        triggers: [u.category].filter(Boolean),
        steps: [],
        enabled: true,
        manual: true,
        category: u.category || '',
      }))
      const seen = new Set(skills.value.map((x: any) => x.name))
      skills.value = [...skills.value, ...manual.filter((m: any) => !seen.has(m.name))]
    }
  } catch { /* keep empty */ } finally { loading.value = false }
}
onMounted(load)

// Category chips (Qoder-style) — derived from manual skill categories.
const activeCategory = ref('')
const categories = computed(() => {
  const set = new Set<string>()
  for (const s of skills.value as any[]) if (s.category) set.add(s.category)
  return [...set]
})
const showCreateCta = computed(() => !loading.value && skills.value.length === 0)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  let list = skills.value
  if (activeCategory.value) list = list.filter((s: any) => s.category === activeCategory.value)
  if (!q) return list
  return list.filter(s =>
    s.name.toLowerCase().includes(q) ||
    s.description.toLowerCase().includes(q) ||
    s.triggers.some(t => t.toLowerCase().includes(q))
  )
})

const stepTypeIcons: Record<string, string> = {
  prompt: 'chat_bubble', tool: 'build', http: 'cloud', condition: 'fork_right',
}
const stepTypeLabels: Record<string, string> = {
  prompt: '提示', tool: '工具', http: 'HTTP', condition: '条件',
}

async function toggleSkill(s: Skill) {
  const next = !s.enabled
  s.enabled = next
  try {
    await fetch(getApiUrl(`/api/agents/skills/${s.id}`), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: next }),
    })
  } catch { s.enabled = !next }
}

async function deleteSkill(id: string) {
  skills.value = skills.value.filter(s => s.id !== id)
  try { await fetch(getApiUrl(`/api/agents/skills/${id}`), { method: 'DELETE' }) } catch {}
}

async function createSkill() {
  if (!draft.value.name.trim()) return
  const triggers = draftTriggers.value.split(',').map(t => t.trim()).filter(Boolean)
  const payload = { name: draft.value.name.trim(), description: draft.value.description, triggers, steps: [], enabled: true }
  try {
    const res = await fetch(getApiUrl('/api/agents/skills'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (res.ok) {
      const created = await res.json()
      skills.value.unshift(created)
    }
  } catch {}
  draft.value = { id: '', name: '', description: '', triggers: [], steps: [], enabled: true }
  draftTriggers.value = ''
  showBuilder.value = false
}
</script>

<template>
  <div class="skill-page">
    <div class="skill-page__inner">
      <div class="skill-page__head">
        <div>
          <h1 class="skill-page__title">技能构建器</h1>
          <p class="skill-page__sub">可视化构建自定义技能 — 拖放步骤、设置触发器</p>
        </div>
        <button class="skill-page__add" @click="showBuilder = !showBuilder">
          <span class="material-symbols-outlined text-[18px]">{{ showBuilder ? 'close' : 'add' }}</span>
          {{ showBuilder ? '取消' : '新建技能' }}
        </button>
      </div>

      <!-- Builder form -->
      <Transition name="skill-slide">
        <div v-if="showBuilder" class="skill-builder">
          <div class="skill-builder__row">
            <label class="skill-builder__label">技能名称</label>
            <input v-model="draft.name" placeholder="例如：自动审查 PR" class="skill-builder__input" />
          </div>
          <div class="skill-builder__row">
            <label class="skill-builder__label">描述</label>
            <input v-model="draft.description" placeholder="这个技能做什么" class="skill-builder__input" />
          </div>
          <div class="skill-builder__row">
            <label class="skill-builder__label">触发关键词（逗号分隔）</label>
            <input v-model="draftTriggers" placeholder="review, 审查, check" class="skill-builder__input" />
          </div>
          <div class="skill-builder__actions">
            <button class="skill-builder__btn" @click="createSkill">保存技能</button>
          </div>
        </div>
      </Transition>

      <!-- Search -->
      <div class="skill-page__tools">
        <div class="skill-search">
          <span class="material-symbols-outlined text-[16px]">search</span>
          <input v-model="search" placeholder="搜索技能..." class="skill-search__input" />
          </div>

          <div v-if="categories.length" class="skill-cats">
            <button
              type="button"
              class="skill-cat"
              :class="{ 'skill-cat--active': activeCategory === '' }"
              @click="activeCategory = ''"
            >全部</button>
            <button
              v-for="c in categories"
              :key="c"
              type="button"
              class="skill-cat"
              :class="{ 'skill-cat--active': activeCategory === c }"
              @click="activeCategory = c"
            >{{ c }}</button>
          </div>

          <div v-if="showCreateCta" class="skill-empty">
            <div class="skill-empty__badge">
              <span class="material-symbols-outlined">auto_awesome</span>
            </div>
            <h3>还没有技能</h3>
            <p>创建第一个技能手册，Agent 会自动在对话中调用它。</p>
            <button class="skill-empty__cta" @click="showBuilder = true">
              <span class="material-symbols-outlined">add</span>
              创建第一个技能
            </button>
          </div>
      </div>

      <!-- Skill list -->
      <div class="skill-list">
        <div v-for="skill in filtered" :key="skill.id" class="skill-card">
          <div class="skill-card__head">
            <div class="skill-card__info">
              <div class="skill-card__name">{{ skill.name }}</div>
              <div class="skill-card__desc">{{ skill.description }}</div>
            </div>
            <div class="skill-card__toggle">
              <div
                class="skill-toggle"
                :class="{ 'skill-toggle--on': skill.enabled }"
                @click="toggleSkill(skill)"
              />
            </div>
          </div>

          <!-- Triggers -->
          <div class="skill-card__section">
            <div class="skill-card__section-label">触发关键词</div>
            <div class="skill-card__tags">
              <span v-for="t in skill.triggers" :key="t" class="skill-card__tag">{{ t }}</span>
            </div>
          </div>

          <!-- Steps -->
          <div class="skill-card__section">
            <div class="skill-card__section-label">执行步骤 ({{ skill.steps.length }})</div>
            <div class="skill-card__steps">
              <div v-for="(step, i) in skill.steps" :key="i" class="skill-step">
                <div class="skill-step__num">{{ i + 1 }}</div>
                <div class="skill-step__icon">
                  <span class="material-symbols-outlined text-[14px]">{{ stepTypeIcons[step.type] }}</span>
                </div>
                <div class="skill-step__body">
                  <div class="skill-step__label">{{ stepTypeLabels[step.type] }}: {{ step.label }}</div>
                  <div class="skill-step__config">{{ step.config }}</div>
                </div>
                <svg class="skill-step__arrow" width="10" height="10" viewBox="0 0 12 12" fill="none">
                  <path d="M3 2L7 6L3 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.4"/>
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skill-page { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.skill-page__inner { max-width: 800px; margin: 0 auto; padding: 24px 20px; }

.skill-page__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.skill-page__title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.skill-page__sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 4px; }
.skill-page__add { display: flex; align-items: center; gap: 6px; padding: 8px 16px; font-size: 13px; font-weight: 500; cursor: pointer; background: var(--color-primary); color: var(--color-on-primary); border: none; }

.skill-builder { background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border); padding: 16px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 12px; }
.skill-builder__row { display: flex; align-items: center; gap: 12px; }
.skill-builder__label { width: 100px; font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.skill-builder__input { flex: 1; padding: 8px 12px; border: 1px solid var(--color-border); background: var(--color-surface); font-size: 13px; color: var(--color-text-primary); outline: none; }
.skill-builder__actions { display: flex; justify-content: flex-end; }
.skill-builder__btn { padding: 8px 20px; background: var(--color-primary); color: var(--color-on-primary); border: none; cursor: pointer; font-size: 13px; font-weight: 500; }

.skill-page__tools { margin-bottom: 16px; }
.skill-search { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1.5px solid var(--color-border); background: var(--color-surface-container-lowest); }
.skill-search__input { flex: 1; border: none; outline: none; background: transparent; font-size: 13px; color: var(--color-text-primary); }

.skill-list { display: flex; flex-direction: column; gap: 12px; }
.skill-card { padding: 16px; background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border); }
.skill-card__head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.skill-card__name { font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
.skill-card__desc { font-size: 12px; color: var(--color-text-tertiary); margin-top: 4px; }
.skill-card__toggle { display: flex; align-items: center; }
.skill-toggle { width: 40px; height: 22px; padding: 2px; background: var(--color-border); cursor: pointer; transition: background 140ms; }
.skill-toggle--on { background: var(--color-primary); }
.skill-toggle::after { content: ''; display: block; width: 18px; height: 18px; background: #fff; transition: transform 140ms; }
.skill-toggle--on::after { transform: translateX(18px); }

.skill-card__section { padding-top: 12px; border-top: 1px solid var(--color-border); margin-top: 12px; }
.skill-card__section-label { font-size: 10px; font-weight: 600; color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
.skill-card__tags { display: flex; flex-wrap: wrap; gap: 4px; }
.skill-card__tag { padding: 2px 8px; font-size: 11px; font-weight: 500; background: var(--color-primary-fixed); color: var(--color-primary); }

.skill-card__steps { display: flex; flex-direction: column; gap: 4px; }
.skill-step { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
.skill-step__num { width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; background: var(--color-primary); color: var(--color-on-primary); font-size: 10px; font-weight: 700; flex-shrink: 0; }
.skill-step__icon { color: var(--color-text-secondary); }
.skill-step__body { flex: 1; min-width: 0; }
.skill-step__label { font-size: 12px; font-weight: 500; color: var(--color-text-primary); }
.skill-step__config { font-size: 10px; color: var(--color-text-tertiary); font-family: var(--font-mono); margin-top: 2px; }
.skill-step__arrow { flex-shrink: 0; color: var(--color-text-tertiary); }

.skill-slide-enter-active, .skill-slide-leave-active { transition: all 200ms; overflow: hidden; }
.skill-slide-enter-from, .skill-slide-leave-to { opacity: 0; max-height: 0; padding: 0; margin: 0; border: none; }

.skill-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0 0 14px;
}
.skill-cat {
  padding: 4px 12px;
  font-size: 12px;
  font-family: inherit;
  color: var(--color-text-secondary);
  background: var(--color-surface-container-low);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.skill-cat:hover { background: var(--color-surface-container-high); color: var(--color-text-primary); }
.skill-cat--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: var(--color-on-primary, #fff);
}
.skill-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 64px 24px;
  text-align: center;
  color: var(--color-text-secondary);
  border: 1.5px dashed var(--color-border);
  border-radius: 16px;
  background: var(--color-surface-container-lowest);
}
.skill-empty__badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: var(--color-primary-container);
  color: var(--color-primary);
  margin-bottom: 4px;
}
.skill-empty__badge .material-symbols-outlined { font-size: 26px; }
.skill-empty h3 { margin: 0; font-size: 16px; font-weight: 600; color: var(--color-text-primary); }
.skill-empty p { margin: 0; font-size: 13px; max-width: 400px; }
.skill-empty__cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  color: var(--color-on-primary, #fff);
  background: var(--color-primary);
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: filter 120ms;
}
.skill-empty__cta:hover { filter: brightness(1.08); }
.skill-empty code {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--color-surface-container-low);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
