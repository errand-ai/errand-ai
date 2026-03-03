import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

function storageGet(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}

function storageSet(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* noop */ }
}

function storageRemove(key: string) {
  try { localStorage.removeItem(key) } catch { /* noop */ }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(storageGet('auth_token'))
  const idToken = ref<string | null>(storageGet('auth_id_token'))
  const refreshToken = ref<string | null>(storageGet('auth_refresh_token'))
  const accessDenied = ref(false)
  const authMode = ref<'setup' | 'local' | 'sso' | null>(null)
  let refreshTimer: ReturnType<typeof setTimeout> | null = null

  const isAuthenticated = computed(() => token.value !== null)

  const userDisplay = computed(() => {
    if (!token.value) return null
    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      return payload.name || payload.preferred_username || payload.email || null
    } catch {
      return null
    }
  })

  const roles = computed<string[]>(() => {
    if (!token.value) return []
    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      // Local auth tokens use _roles claim directly
      if (Array.isArray(payload._roles)) return payload._roles
      // SSO tokens use resource_access
      const clientId = payload?.azp ?? 'errand'
      const clientRoles = payload?.resource_access?.[clientId]?.roles
      return Array.isArray(clientRoles) ? clientRoles : []
    } catch {
      return []
    }
  })

  function setAuthMode(mode: 'setup' | 'local' | 'sso') {
    authMode.value = mode
  }

  const isAdmin = computed(() => roles.value.includes('admin'))
  const isEditor = computed(() => roles.value.includes('editor') || roles.value.includes('admin'))
  const isViewer = computed(() => isAuthenticated.value && !isEditor.value)

  function scheduleRefresh() {
    cancelRefresh()
    if (!token.value || !refreshToken.value) return

    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      const exp = payload.exp
      if (!exp) return

      const msUntilExpiry = exp * 1000 - Date.now()
      const msUntilRefresh = msUntilExpiry - 30_000 // 30 seconds before expiry

      if (msUntilRefresh <= 0) {
        // Token already near expiry — refresh immediately
        doRefresh()
        return
      }

      refreshTimer = setTimeout(doRefresh, msUntilRefresh)
    } catch {
      // Can't decode token — skip scheduling
    }
  }

  function cancelRefresh() {
    if (refreshTimer !== null) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
  }

  async function doRefresh() {
    if (!refreshToken.value) return

    try {
      const resp = await fetch('/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken.value }),
      })

      if (!resp.ok) return

      const data = await resp.json()
      token.value = data.access_token
      if (data.id_token) idToken.value = data.id_token
      if (data.refresh_token) refreshToken.value = data.refresh_token
      accessDenied.value = false

      scheduleRefresh()
    } catch {
      // Refresh failed — don't redirect, let the 401 retry handle it
    }
  }

  function setToken(t: string, id?: string, rt?: string) {
    token.value = t
    idToken.value = id ?? null
    refreshToken.value = rt ?? null
    accessDenied.value = false
    storageSet('auth_token', t)
    if (id) storageSet('auth_id_token', id)
    else storageRemove('auth_id_token')
    if (rt) storageSet('auth_refresh_token', rt)
    else storageRemove('auth_refresh_token')
    scheduleRefresh()
  }

  function clearToken() {
    cancelRefresh()
    token.value = null
    idToken.value = null
    refreshToken.value = null
    storageRemove('auth_token')
    storageRemove('auth_id_token')
    storageRemove('auth_refresh_token')
  }

  function setAccessDenied() {
    accessDenied.value = true
  }

  // If a token was restored from localStorage, schedule refresh
  if (token.value) {
    scheduleRefresh()
  }

  return { token, idToken, refreshToken, isAuthenticated, accessDenied, authMode, userDisplay, roles, isAdmin, isEditor, isViewer, setToken, clearToken, setAccessDenied, setAuthMode, scheduleRefresh, cancelRefresh, doRefresh }
})
