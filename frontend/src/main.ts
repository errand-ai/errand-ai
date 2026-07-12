import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import { createErrandUI, createDirectApi, type ServerCapabilities } from '@errand-ai/ui-components'
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
    auth.redirectToLogin()
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

// Server capabilities gate which shared settings cards render (e.g. CloudStorageCard,
// LitellmMcpCard). The endpoint is public, so we fetch it fire-and-forget at bootstrap;
// the reactive ref updates the injected capabilities and gated cards re-render on arrival.
// If the fetch fails the defaults leave optional cards hidden rather than erroring.
const capabilities = ref<ServerCapabilities>({ version: null, capabilities: [], connected: false })

fetch('/api/capabilities')
  .then((resp) => (resp.ok ? resp.json() : null))
  .then((data) => {
    // Only mark connected on a well-formed, non-empty capabilities array. The
    // library treats an EMPTY list as "capability info unavailable" and renders
    // gated cards permissively, so on a missing/malformed/empty response we keep
    // the initial disconnected state (gated cards stay hidden) rather than
    // flipping every optional card on.
    if (data && Array.isArray(data.capabilities) && data.capabilities.length > 0) {
      capabilities.value = {
        version: data.version ?? null,
        capabilities: data.capabilities,
        connected: true,
      }
    }
  })
  .catch(() => {
    /* leave defaults — capability-gated cards stay hidden */
  })

const errandUI = createErrandUI({ api, capabilities })
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- npm link causes duplicate Vue type trees
app.use({ install: (a: any) => errandUI.install(a) })
app.mount('#app')
