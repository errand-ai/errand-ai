<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useTaskStore } from './stores/tasks'
import { HeaderBar } from '@errand-ai/ui-components'
import AccessDenied from './components/AccessDenied.vue'
import { Toaster } from 'vue-sonner'
import 'vue-sonner/style.css'

const auth = useAuthStore()
const taskStore = useTaskStore()
const route = useRoute()
const router = useRouter()
const dropdownOpen = ref(false)
const booting = ref(true)
const versionInfo = ref<{ current: string; latest: string | null; update_available: boolean } | null>(null)

const showCloudIndicator = computed(() => taskStore.cloudStatus !== 'not_configured')
const cloudConnected = computed(() => taskStore.cloudStatus === 'connected')
const cloudStatusText = computed(() => {
  if (cloudConnected.value) return 'Connected'
  if (taskStore.cloudStatus === 'error') return 'Reconnect'
  return 'Disconnected'
})

const navLinks = computed(() => {
  const links: { label: string; to: string }[] = [
    { label: 'Board', to: '/' },
    { label: 'Archived', to: '/archived' },
  ]
  if (auth.isAdmin) {
    links.push({ label: 'Settings', to: '/settings' })
  }
  return links
})

onMounted(async () => {
  // 1. Check for OIDC callback tokens in URL fragment
  const hash = window.location.hash
  if (hash) {
    const params = new URLSearchParams(hash.substring(1))
    const accessToken = params.get('access_token')
    if (accessToken) {
      auth.setToken(accessToken, params.get('id_token') ?? undefined, params.get('refresh_token') ?? undefined)
      history.replaceState(null, '', window.location.pathname)
    }
  }

  // 2. Fetch auth status
  try {
    const resp = await fetch('/api/auth/status')
    const data = await resp.json()
    auth.setAuthMode(data.mode)

    switch (data.mode) {
      case 'setup':
        router.push('/setup')
        break
      case 'local':
        if (!auth.isAuthenticated) {
          router.push('/login')
        }
        break
      case 'sso':
        if (!auth.isAuthenticated) {
          window.location.href = data.login_url || '/auth/login'
        }
        break
    }
  } catch {
    // Fallback — can't determine auth mode
    console.error('Failed to fetch auth status')
  } finally {
    booting.value = false
  }

  // Fetch version info (no auth required, failure is silent)
  try {
    const vResp = await fetch('/api/version')
    if (vResp.ok) {
      versionInfo.value = await vResp.json()
    }
  } catch {
    // Version display is optional — hide on failure
  }

  await fetchCloudStatus()
})

async function fetchCloudStatus() {
  if (!auth.isAuthenticated || !auth.token) return
  try {
    const cResp = await fetch('/api/cloud/status', {
      headers: { 'Authorization': `Bearer ${auth.token}` },
    })
    if (cResp.ok) {
      const cData = await cResp.json()
      taskStore.cloudStatus = cData.status ?? 'not_configured'
    }
  } catch {
    // Cloud status is optional — hide on failure
  }
}

// Re-fetch cloud status when user authenticates (e.g. after local login)
watch(() => auth.isAuthenticated, (authenticated) => {
  if (authenticated) fetchCloudStatus()
})

function logout() {
  if (auth.authMode === 'sso') {
    const params = auth.idToken ? `?id_token_hint=${encodeURIComponent(auth.idToken)}` : ''
    window.location.href = `/auth/logout${params}`
  } else {
    auth.clearToken()
    router.push('/login')
  }
}

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value
}

function closeDropdown() {
  dropdownOpen.value = false
}

function handleClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (dropdownOpen.value && !target.closest('.dropdown-trigger')) {
    closeDropdown()
  }
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onUnmounted(() => document.removeEventListener('click', handleClickOutside))
</script>

<template>
  <Toaster position="top-right" />

  <!-- Unauthenticated routes render their own full-page layout -->
  <router-view v-if="route.name === 'login' || route.name === 'setup'" />

  <!-- Authenticated app layout -->
  <div v-else-if="!booting && auth.isAuthenticated" class="min-h-screen bg-gray-100">
    <HeaderBar
      logo="/logo.png"
      title="Errand AI"
      subtitle="Your personal assistant"
      :links="navLinks"
      :active-route="route.path"
    >
      <template #right>
        <router-link
          v-if="showCloudIndicator"
          to="/settings/cloud"
          class="flex items-center gap-1.5 text-sm"
          :class="cloudConnected ? 'text-green-600' : taskStore.cloudStatus === 'error' ? 'text-red-500' : 'text-amber-500'"
          data-testid="cloud-indicator"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 .75-7.425A4.502 4.502 0 0 0 13.5 6 4.5 4.5 0 0 0 9.307 8.593 4.501 4.501 0 0 0 2.25 15Z" />
          </svg>
          {{ cloudStatusText }}
        </router-link>
        <span v-if="versionInfo?.current" class="flex items-center gap-1.5 text-sm text-gray-400" data-testid="version-display">
          {{ versionInfo.current.match(/^\d/) ? `v${versionInfo.current}` : versionInfo.current }}
          <span
            v-if="versionInfo.update_available"
            class="inline-block h-2 w-2 rounded-full bg-amber-500"
            :title="`v${versionInfo.latest} available`"
            data-testid="update-indicator"
          ></span>
        </span>
        <a href="https://github.com/errand-ai" target="_blank" rel="noopener noreferrer" class="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900">
          <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12Z"/></svg>
          GitHub
        </a>
        <template v-if="auth.userDisplay">
          <div class="relative dropdown-trigger">
            <button
              @click="toggleDropdown"
              class="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
            >
              {{ auth.userDisplay }}
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            <div
              v-if="dropdownOpen"
              class="absolute right-0 mt-2 w-48 rounded-md bg-white py-1 shadow-lg ring-1 ring-black/5 z-50"
            >
              <button
                @click="logout"
                class="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
              >
                Log out
              </button>
            </div>
          </div>
        </template>
        <template v-else>
          <button
            @click="logout"
            class="rounded-md bg-gray-800 px-3 py-1.5 text-sm text-white hover:bg-gray-700"
          >
            Log out
          </button>
        </template>
      </template>
    </HeaderBar>
    <main class="px-4 py-6">
      <AccessDenied v-if="auth.accessDenied" />
      <router-view v-else />
    </main>
  </div>
</template>
