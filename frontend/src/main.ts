import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createErrandUI, createDirectApi } from '@errand-ai/ui-components'
import router from './router'
import App from './App.vue'
import { useAuthStore } from './stores/auth'
import './assets/main.css'

const pinia = createPinia()
const app = createApp(App)
app.use(pinia)
app.use(router)

// Initialize auth store so it's available for the API adapter
const auth = useAuthStore()

const api = createDirectApi({
  baseUrl: '/api',
  getToken: () => auth.token,
  onUnauthorized: () => {
    auth.clearToken()
    window.location.href = '/auth/login'
  },
  onForbidden: () => {
    auth.setAccessDenied()
  },
  refreshToken: async () => {
    if (!auth.refreshToken) return false
    try {
      const resp = await fetch('/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: auth.refreshToken }),
      })
      if (!resp.ok) return false
      const data = await resp.json()
      auth.setToken(data.access_token, data.id_token, data.refresh_token)
      return true
    } catch {
      return false
    }
  },
})

const errandUI = createErrandUI({ api })
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- npm link causes duplicate Vue type trees
app.use({ install: (a: any) => errandUI.install(a) })
app.mount('#app')
