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