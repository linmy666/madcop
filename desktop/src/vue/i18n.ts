import { ref } from 'vue'
import { defineStore } from 'pinia'
import { zh as ZH_FULL } from '../i18n/locales/zh'
import { en as EN_FULL } from '../i18n/locales/en'

// v3.0 — Vue i18n bridge (with real translations from React locale files)
// Loads the actual Chinese/English translation texts so sidebar buttons show
// proper labels ("新建会话") instead of i18n keys ("sidebar.newSession").

export type Locale = 'zh' | 'en'
export type TranslationKey = string

// Load the full translation tables from the real locale files.
const ZH: Record<string, string> = ZH_FULL as any
const EN: Record<string, string> = EN_FULL as any

// Pinia-backed locale: useI18nStore().locale is reactive state, so
// every component that calls useTranslation() inside a template
// re-renders when the user switches language. The module ref is
// kept as a side channel for non-React callers (chatStore) that
// need the current locale synchronously without going through Pinia.
const _activeLocale = ref<Locale>('en')

export const useI18nStore = defineStore('i18n', {
  state: () => ({ locale: 'en' as Locale }),
  actions: {
    setLocale(l: Locale) {
      this.locale = l
      _activeLocale.value = l
    },
  },
})

// Legacy module-level setter (settingsStore + chatStore use this).
export function setLocale(locale: Locale) {
  _activeLocale.value = locale
}

export function getCurrentLocale(): Locale {
  return _activeLocale.value
}

export function translate(
  locale: Locale,
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  let table: Record<string, string>
  switch (locale) {
    case 'en': table = EN; break
    default: table = ZH; break
  }
  let text = table[key] || key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v)).replace(`{count}`, String(v))
    }
  }
  return text
}

// Plain t() — reads the current locale from the Pinia store when
// available, falls back to the module ref. Returns the supplied
// fallback (instead of the raw key) when the table doesn't have it.
export function t(
  key: TranslationKey,
  fallback: string = key,
  params?: Record<string, string | number>,
): string {
  let locale: Locale = 'en'
  try { locale = useI18nStore().locale } catch { locale = _activeLocale.value }
  const text = translate(locale, key, params)
  return text && text !== key ? text : fallback
}

// Returns a callable function that auto-re-renders on locale change.
// Reading the Pinia state inside this composable registers the
// dependency with Vue's reactivity system, so a locale change in
// the store triggers a re-render in every component that called it.
export function useTranslation(): ((key: TranslationKey, params?: Record<string, string | number>) => string) & {
  t: typeof t
  translate: typeof translate
} {
  // Touch the reactive state so this composable participates in
  // the component's render scope (Vue 3 dependency tracking).
  const i18n = useI18nStore()
  void i18n.locale
  const fn = ((key: TranslationKey, params?: Record<string, string | number>) =>
    translate(i18n.locale, key, params) || key) as any
  fn.t = t
  fn.translate = translate
  return fn
}
