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