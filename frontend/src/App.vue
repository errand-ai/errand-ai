<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import AccessDenied from './components/AccessDenied.vue'

const auth = useAuthStore()
const router = useRouter()
const dropdownOpen = ref(false)

onMounted(() => {
  // Extract token from URL fragment after OIDC callback
  const hash = window.location.hash
  if (hash) {
    const params = new URLSearchParams(hash.substring(1))
    const token = params.get('access_token')
    if (token) {
      auth.setToken(token, params.get('id_token') ?? undefined, params.get('refresh_token') ?? undefined)
      history.replaceState(null, '', window.location.pathname)
      return
    }
  }

  // No token — redirect to login
  if (!auth.isAuthenticated) {
    window.location.href = '/auth/login'
  }
})

function logout() {
  const params = auth.idToken ? `?id_token_hint=${encodeURIComponent(auth.idToken)}` : ''
  window.location.href = `/auth/logout${params}`
}

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value
}

function closeDropdown() {
  dropdownOpen.value = false
}

function goToSettings() {
  closeDropdown()
  router.push('/settings')
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
  <div class="min-h-screen bg-gray-100" v-if="auth.isAuthenticated">
    <header class="bg-white shadow">
      <div class="flex items-center justify-between px-4 py-4">
        <div class="flex items-center gap-3">
          <router-link to="/" class="flex items-center gap-3">
            <img src="/logo.png" alt="Logo" class="h-8 w-auto" />
            <h1 class="text-2xl font-bold text-gray-900">Content Manager</h1>
          </router-link>
        </div>
        <div class="flex items-center gap-4">
          <!-- Admin: dropdown menu -->
          <template v-if="auth.isAdmin && auth.userDisplay">
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
                  @click="goToSettings"
                  class="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                >
                  Settings
                </button>
                <button
                  @click="logout"
                  class="block w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
                >
                  Log out
                </button>
              </div>
            </div>
          </template>
          <!-- Non-admin: static layout -->
          <template v-else>
            <span v-if="auth.userDisplay" class="text-sm text-gray-600">{{ auth.userDisplay }}</span>
            <button
              @click="logout"
              class="rounded-md bg-gray-800 px-3 py-1.5 text-sm text-white hover:bg-gray-700"
            >
              Log out
            </button>
          </template>
        </div>
      </div>
    </header>
    <main class="px-4 py-6">
      <AccessDenied v-if="auth.accessDenied" />
      <router-view v-else />
    </main>
  </div>
</template>
