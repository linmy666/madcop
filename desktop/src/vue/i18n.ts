// v3.0 — Vue i18n bridge (with real translations from React locale files)
// Loads the actual Chinese/English translation texts so sidebar buttons show
// proper labels ("新建会话") instead of i18n keys ("sidebar.newSession").

import { ref } from 'vue'
import { zh as ZH_FULL } from '../i18n/locales/zh'
import { en as EN_FULL } from '../i18n/locales/en'

export type Locale = 'zh' | 'en' | 'jp' | 'kr' | 'zh-TW'
export type TranslationKey = string

// Load the full translation tables from the real locale files.
// These are the same .ts files that the React app uses.
const ZH: Record<string, string> = ZH_FULL as any
const EN: Record<string, string> = EN_FULL as any

// Module-level locale and translation table
const currentLocale = ref<Locale>('zh')
const translations = ref<Record<string, string>>(ZH)

export function setLocale(locale: Locale) {
  currentLocale.value = locale
  switch (locale) {
    case 'en': translations.value = EN; break
    default: translations.value = ZH; break
  }
}

// Module-level t (callable as plain function)
export function t(key: TranslationKey, params?: Record<string, string | number>): string {
  let text = translations.value[key] || key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v)).replace(`{count}`, String(v))
    }
  }
  return text
}

export function translate(locale: Locale, key: TranslationKey, params?: Record<string, string | number>): string {
  return t(key, params)
}

// Returns a callable function — `const t = useTranslation(); t('key')` works
export function useTranslation(): ((key: TranslationKey, params?: Record<string, string | number>) => string) & {
  t: typeof t
  translate: typeof translate
} {
  const fn = t as any
  fn.t = t
  fn.translate = translate
  return fn
}