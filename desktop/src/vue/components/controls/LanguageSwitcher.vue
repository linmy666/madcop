<script setup lang="ts">
/**
 * LanguageSwitcher — top-bar toggle for zh / en. Wired into the
 * settingsStore locale so every useTranslation() consumer re-renders
 * instantly on change.
 */
import { useSettingsStore } from '../../stores/settingsStore'
import { setLocale as i18nSetLocale } from '../../i18n'

const settings = useSettingsStore()
const t = (lang: 'zh' | 'en') => (lang === 'zh' ? '中文' : 'EN')

function pick(lang: 'zh' | 'en') {
  if (settings.locale === lang) return
  settings.setLocale(lang)
  i18nSetLocale(lang)
}
</script>

<template>
  <div class="lang-switch" role="group" aria-label="Language">
    <button
      type="button"
      class="lang-switch__btn"
      :class="{ 'lang-switch__btn--active': settings.locale === 'zh' }"
      :aria-pressed="settings.locale === 'zh'"
      data-testid="lang-zh"
      @click="pick('zh')"
    >{{ t('zh') }}</button>
    <button
      type="button"
      class="lang-switch__btn"
      :class="{ 'lang-switch__btn--active': settings.locale === 'en' }"
      :aria-pressed="settings.locale === 'en'"
      data-testid="lang-en"
      @click="pick('en')"
    >{{ t('en') }}</button>
  </div>
</template>

<style scoped>
.lang-switch {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--color-border, rgba(128, 128, 128, 0.25));
  border-radius: 999px;
  padding: 2px;
  background: var(--color-surface-container-low, transparent);
}
.lang-switch__btn {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--color-text-secondary, #555);
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 999px;
  cursor: pointer;
  font-family: inherit;
  transition: background-color 120ms, color 120ms;
}
.lang-switch__btn:hover {
  color: var(--color-text-primary, #111);
}
.lang-switch__btn--active {
  background: var(--color-primary, #7c5cff);
  color: var(--color-on-primary, #fff);
}
</style>
