import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const idToken = ref<string | null>(null)
  const accessDenied = ref(false)

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

  function setToken(t: string, id?: string) {
    token.value = t
    idToken.value = id ?? null
    accessDenied.value = false
  }

  function clearToken() {
    token.value = null
    idToken.value = null
  }

  function setAccessDenied() {
    accessDenied.value = true
  }

  return { token, idToken, isAuthenticated, accessDenied, userDisplay, setToken, clearToken, setAccessDenied }
})
