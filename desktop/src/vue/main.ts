import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import '../theme/globals.css'

const app = createApp(App)
app.use(createPinia())
app.mount('#root')
