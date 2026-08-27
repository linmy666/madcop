import { createApp } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
// Must be imported before App so the global /api fetch shim is installed
// before any component mounts and issues a request.
import './api/client'
import App from './App.vue'
import '../theme/globals.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
// v3.0: explicitly set the active pinia at module scope so async
// chunks (PluginSettings, PluginList, etc.) can find it via
// getActivePinia() during their setup phase.
setActivePinia(pinia)
app.mount('#root')

// Restore the persisted UI locale into the i18n store. The i18n store
// itself is memory-only and starts at 'en' every boot; without this
// sync a user who picked 中文 last session gets a Chinese settings
// page (settingsStore-driven) beside an English sidebar (i18n-driven).
import { useSettingsStore } from './stores/settingsStore'
import { setLocale as i18nSetLocale } from './i18n'
const _settings = useSettingsStore()
if (_settings.locale === 'zh' || _settings.locale === 'en') {
  i18nSetLocale(_settings.locale)
}

// A crash or force-quit leaves stale 'running' markers in the persisted
// tab/chat stores; nothing survives a restart, so reset them before the
// sidebar renders — otherwise hours-old sessions show a live dot.
import { useTabStore } from './stores/tabs'
import { useChatStore } from './stores/chatStore'
try {
  const _tabs = useTabStore()
  for (const tb of _tabs.tabs) {
    if (tb.status === 'running') _tabs.setTabStatus(tb.sessionId, 'idle')
  }
  const _chat = useChatStore()
  for (const s of Object.values(_chat.sessions) as Array<{ chatState: string }>) {
    if (s.chatState && s.chatState !== 'idle') s.chatState = 'idle'
  }
} catch { /* stores not hydrated yet — first boot */ }