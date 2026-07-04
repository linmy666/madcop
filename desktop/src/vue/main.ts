// MadCop Vue 3 entry — to be wired into Electron main.cjs later.
// For now this file exists as a "type-check" target: vue-tsc
// compiles it but Electron still loads the React App.tsx.

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import '../theme/madcop.css'  // reuse the existing MadCop CSS so visual identity carries over

const app = createApp(App)
app.use(createPinia())
app.mount('#root')
