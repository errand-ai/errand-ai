<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    const resp = await fetch('/auth/local/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      errorMsg.value = data.detail || 'Invalid username or password.'
      return
    }
    const data = await resp.json()
    auth.setToken(data.access_token)
    router.push('/')
  } catch {
    errorMsg.value = 'Unable to connect. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100">
    <div class="max-w-md w-full bg-white rounded-lg shadow p-8">
      <div class="text-center mb-6">
        <img src="/logo.png" alt="Logo" class="h-16 mx-auto mb-4" />
        <h1 class="text-2xl font-bold text-gray-900">Sign in to Errand</h1>
      </div>
      <form @submit.prevent="handleLogin" class="space-y-4" data-testid="login-form">
        <div>
          <label class="block text-sm font-medium text-gray-700">Username</label>
          <input
            v-model="username"
            type="text"
            required
            autocomplete="username"
            data-testid="login-username"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">Password</label>
          <input
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            data-testid="login-password"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          />
        </div>
        <div v-if="errorMsg" class="text-sm text-red-600" data-testid="login-error">{{ errorMsg }}</div>
        <button
          type="submit"
          :disabled="loading"
          data-testid="login-submit"
          class="w-full rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
        >
          {{ loading ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>
    </div>
  </div>
</template>
