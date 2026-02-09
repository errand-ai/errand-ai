<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import KanbanBoard from './components/KanbanBoard.vue'
import AccessDenied from './components/AccessDenied.vue'

const auth = useAuthStore()

onMounted(() => {
  // Extract token from URL fragment after OIDC callback
  const hash = window.location.hash
  if (hash) {
    const params = new URLSearchParams(hash.substring(1))
    const token = params.get('access_token')
    if (token) {
      auth.setToken(token, params.get('id_token') ?? undefined)
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
</script>

<template>
  <div class="min-h-screen bg-gray-100" v-if="auth.isAuthenticated">
    <header class="bg-white shadow">
      <div class="flex items-center justify-between px-4 py-4">
        <div class="flex items-center gap-3">
          <img src="/logo.png" alt="Logo" class="h-8 w-auto" />
          <h1 class="text-2xl font-bold text-gray-900">Content Manager</h1>
        </div>
        <div class="flex items-center gap-4">
          <span v-if="auth.userDisplay" class="text-sm text-gray-600">{{ auth.userDisplay }}</span>
          <button
            @click="logout"
            class="rounded-md bg-gray-800 px-3 py-1.5 text-sm text-white hover:bg-gray-700"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
    <main class="px-4 py-6">
      <AccessDenied v-if="auth.accessDenied" />
      <KanbanBoard v-else />
    </main>
  </div>
</template>
