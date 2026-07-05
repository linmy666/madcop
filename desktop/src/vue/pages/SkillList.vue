<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useSkillStore } from '../stores/skillStore'
import { useSessionStore } from '../stores/sessionStore'
import { useTranslation } from '../../i18n'
import type { SkillSource } from '../stores/skillStore'
import type { SkillDefinition } from '../stores/skillStore'

const SOURCE_ORDER: SkillSource[] = ['user', 'project', 'plugin', 'mcp', 'bundled']

const SOURCE_ICONS: Record<SkillSource, string> = {
  user: 'person',
  project: 'folder',
  plugin: 'extension',
  mcp: 'hub',
  bundled: 'inventory_2',
}

const SOURCE_ACCENT_CLASSES: Record<SkillSource, string> = {
  user: 'bg-[var(--color-primary-fixed)] text-[var(--color-brand)]',
  project: 'bg-[var(--color-success-container)] text-[var(--color-success)]',
  plugin: 'bg-[var(--color-warning-container)] text-[var(--color-warning)]',
  mcp: 'bg-[var(--color-info-container)] text-[var(--color-info)]',
  bundled: 'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]',
}

function estimateTokens(contentLength: number) {
  return Math.ceil(contentLength / 4)
}

const skillStore = useSkillStore()
const sessionStore = useSessionStore()
const t = useTranslation()

const sessions = computed(() => sessionStore.sessions)
const activeSessionId = computed(() => sessionStore.activeSessionId)
const activeSession = computed(
  () => sessions.value.find((session) => session.id === activeSessionId.value),
)
const currentWorkDir = computed(() => activeSession.value?.workDir || undefined)

const searchQuery = ref('')
const normalizedSearchQuery = computed(() => searchQuery.value.trim().toLocaleLowerCase())

onMounted(() => {
  void skillStore.fetchSkills(currentWorkDir.value)
})

// Re-fetch when workDir changes (mirror React useEffect dependency)
watch(currentWorkDir, (wd) => {
  void skillStore.fetchSkills(wd)
})

const skills = computed(() => skillStore.skills)

const filteredSkills = computed(() => {
  if (!normalizedSearchQuery.value) return skills.value

  return skills.value.filter((skill) => {
    const fields = [
      skill.name,
      skill.displayName,
      skill.description,
      skill.source,
      t(`settings.skills.source.${skill.source}`),
      skill.version ?? '',
      skill.pluginName ?? '',
    ]

    return fields.some(
      (field) => field != null && field.toLocaleLowerCase().includes(normalizedSearchQuery.value),
    )
  })
})

const grouped = computed(() => {
  const result: Partial<Record<SkillSource, SkillDefinition[]>> = {}
  for (const skill of filteredSkills.value) {
    const src = skill.source as SkillSource
    ;(result[src] ??= []).push(skill)
  }
  return result
})

const totalTokens = computed(() =>
  filteredSkills.value.reduce((sum, skill) => sum + estimateTokens(skill.contentLength), 0),
)

const visibleGroupCount = computed(() =>
  SOURCE_ORDER.filter((source) => (grouped.value[source] ?? []).length > 0).length,
)

function handleSkillClick(
  skill: SkillDefinition,
  source: SkillSource,
  currentDir?: string,
) {
  if (skill.hasDirectory) {
    void skillStore.fetchSkillDetail(source, skill.name, currentDir, 'skills')
  }
}

// SummaryCard is rendered inline via <template> since it's a local component.
// Props passed via v-bind in the template below.
</script>

<template>
  <div v-if="skillStore.isLoading" class="flex justify-center py-12">
    <div
      class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full"
    />
  </div>

  <div v-else-if="skillStore.error" class="text-sm text-[var(--color-error)] py-4">
    {{ skillStore.error }}
  </div>

  <div
    v-else-if="skills.length === 0"
    class="text-center py-12 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-6"
  >
    <span
      class="material-symbols-outlined text-[40px] text-[var(--color-text-tertiary)] mb-2 block"
    >
      auto_awesome
    </span>
    <p class="text-sm text-[var(--color-text-tertiary)]">
      {{ t('settings.skills.empty') }}
    </p>
    <p class="text-xs text-[var(--color-text-tertiary)] mt-1">
      {{ t('settings.skills.emptyHint') }}
    </p>
  </div>

  <div v-else class="flex flex-col gap-6 min-w-0">
    <section
      class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden"
    >
      <div
        class="grid gap-4 px-5 py-5 min-w-0 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,1fr)] xl:items-end"
      >
        <div class="min-w-0">
          <div
            class="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--color-text-tertiary)] mb-2"
          >
            {{ t('settings.skills.browserEyebrow') }}
          </div>
          <div class="flex items-center gap-3 mb-2">
            <span class="material-symbols-outlined text-[22px] text-[var(--color-brand)]">
              auto_awesome
            </span>
            <h3 class="text-lg font-semibold text-[var(--color-text-primary)]">
              {{ t('settings.skills.browserTitle') }}
            </h3>
          </div>
          <p class="text-sm leading-6 text-[var(--color-text-secondary)] max-w-3xl">
            {{ t('settings.skills.browserDescription') }}
          </p>
          <div class="mt-4 max-w-2xl">
            <label class="sr-only" for="settings-skill-search">
              {{ t('settings.skills.searchLabel') }}
            </label>
            <div
              class="flex min-h-11 items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 transition-colors focus-within:border-[var(--color-border-focus)] focus-within:ring-2 focus-within:ring-[var(--color-brand)]/20"
            >
              <span
                class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]"
              >
                search
              </span>
              <input
                id="settings-skill-search"
                :value="searchQuery"
                @input="($event as any).target.value !== undefined && (searchQuery = ($event as any).target.value)"
                :placeholder="t('settings.skills.searchPlaceholder')"
                class="min-w-0 flex-1 bg-transparent text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
              />
              <button
                v-if="searchQuery"
                type="button"
                :aria-label="t('settings.skills.clearSearch')"
                @click="searchQuery = ''"
                class="inline-flex h-7 w-7 items-center justify-center rounded-full text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
              >
                <span class="material-symbols-outlined text-[16px]">close</span>
              </button>
            </div>
            <p
              v-if="normalizedSearchQuery"
              class="mt-2 text-[11px] text-[var(--color-text-tertiary)]"
            >
              {{
                t('settings.skills.searchResultCount', {
                  count: String(filteredSkills.length),
                  total: String(skills.length),
                })
              }}
            </p>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3 min-w-0 sm:grid-cols-3">
          <div
            class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 min-w-0"
          >
            <div
              class="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] min-w-0"
            >
              <span
                class="material-symbols-outlined text-[14px] flex-shrink-0"
              >auto_awesome</span>
              <span class="truncate">
                {{ t('settings.skills.summary.totalSkills') }}
              </span>
            </div>
            <div
              class="mt-2 text-lg font-semibold text-[var(--color-text-primary)] truncate"
            >
              {{ String(filteredSkills.length) }}
            </div>
          </div>

          <div
            class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 min-w-0"
          >
            <div
              class="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] min-w-0"
            >
              <span
                class="material-symbols-outlined text-[14px] flex-shrink-0"
              >layers</span>
              <span class="truncate">
                {{ t('settings.skills.summary.sources') }}
              </span>
            </div>
            <div
              class="mt-2 text-lg font-semibold text-[var(--color-text-primary)] truncate"
            >
              {{
                String(
                  SOURCE_ORDER.filter(
                    (source) => (grouped[source] ?? []).length > 0,
                  ).length,
                )
              }}
            </div>
          </div>

          <div
            class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3 min-w-0 col-span-2 sm:col-span-1"
          >
            <div
              class="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--color-text-tertiary)] min-w-0"
            >
              <span
                class="material-symbols-outlined text-[14px] flex-shrink-0"
              >notes</span>
              <span class="truncate">
                {{ t('settings.skills.summary.tokens') }}
              </span>
            </div>
            <div
              class="mt-2 text-lg font-semibold text-[var(--color-text-primary)] truncate"
            >
              {{ t('settings.skills.tokenEstimateShort', { count: String(totalTokens) }) }}
            </div>
          </div>
        </div>
      </div>
    </section>

    <div
      v-if="filteredSkills.length === 0"
      class="text-center py-12 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-6"
    >
      <span
        class="material-symbols-outlined text-[40px] text-[var(--color-text-tertiary)] mb-2 block"
      >
        search_off
      </span>
      <p class="text-sm text-[var(--color-text-tertiary)]">
        {{ t('settings.skills.noSearchResults') }}
      </p>
      <p class="text-xs text-[var(--color-text-tertiary)] mt-1">
        {{ t('settings.skills.noSearchResultsHint') }}
      </p>
    </div>

    <div
      :class="`grid gap-4 ${visibleGroupCount >= 2 ? 'xl:grid-cols-2' : ''}`"
    >
      <template v-for="source in SOURCE_ORDER" :key="source">
        <section
          v-if="grouped[source] && grouped[source]!.length"
          class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden min-w-0"
        >
          <div
            class="flex items-start justify-between gap-3 px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)]"
          >
            <div class="min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span
                  class="inline-flex h-7 w-7 items-center justify-center rounded-full"
                  :class="SOURCE_ACCENT_CLASSES[source]"
                >
                  <span class="material-symbols-outlined text-[16px]">
                    {{ SOURCE_ICONS[source] }}
                  </span>
                </span>
                <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
                  {{ t(`settings.skills.source.${source}`) }}
                </h4>
                <span class="text-xs text-[var(--color-text-tertiary)]">
                  {{ grouped[source]!.length }}
                </span>
              </div>
              <p class="text-xs leading-5 text-[var(--color-text-tertiary)]">
                {{
                  t('settings.skills.groupHint', {
                    source: t(`settings.skills.source.${source}`),
                    count: String(grouped[source]!.length),
                  })
                }}
              </p>
            </div>
            <div class="text-[11px] text-[var(--color-text-tertiary)] whitespace-nowrap">
              {{
                t('settings.skills.tokenEstimateShort', {
                  count: String(
                    grouped[source]!.reduce(
                      (sum, skill) => sum + estimateTokens(skill.contentLength),
                      0,
                    ),
                  ),
                })
              }}
            </div>
          </div>

          <div class="flex flex-col p-2">
            <template v-for="skill in grouped[source]!" :key="`${skill.source}-${skill.name}`">
              <button
                @click="handleSkillClick(skill, source, currentWorkDir)"
                :disabled="!skill.hasDirectory"
                class="group rounded-xl border border-transparent px-3 py-3 text-left transition-all hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:opacity-60 disabled:cursor-default disabled:hover:bg-transparent disabled:hover:border-transparent"
              >
                <div class="flex items-start gap-3">
                  <span
                    class="mt-0.5 material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]"
                  >
                    auto_awesome
                  </span>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 flex-wrap">
                      <span
                        class="text-sm font-semibold text-[var(--color-text-primary)] break-all"
                      >
                        {{ skill.displayName || skill.name }}
                      </span>
                      <span
                        v-if="skill.version"
                        class="rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]"
                      >
                        v{{ skill.version }}
                      </span>
                      <span
                        v-if="skill.userInvocable"
                        class="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]"
                      >
                        {{ t('settings.skills.slashCommand') }}
                      </span>
                    </div>
                    <p
                      class="mt-1 text-xs leading-5 text-[var(--color-text-secondary)] break-words"
                    >
                      {{ skill.description }}
                    </p>
                    <div
                      class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--color-text-tertiary)]"
                    >
                      <span>{{ t(`settings.skills.source.${skill.source}`) }}</span>
                      <span>
                        {{
                          t('settings.skills.tokenEstimateShort', {
                            count: String(estimateTokens(skill.contentLength)),
                          })
                        }}
                      </span>
                      <span>
                        {{
                          skill.hasDirectory
                            ? t('settings.skills.ready')
                            : t('settings.skills.unavailable')
                        }}
                      </span>
                    </div>
                  </div>
                  <span
                    class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)] opacity-60 transition-transform group-hover:translate-x-0.5 group-hover:opacity-100"
                  >
                    chevron_right
                  </span>
                </div>
              </button>
            </template>
          </div>
        </section>
      </template>
    </div>
  </div>
</template>