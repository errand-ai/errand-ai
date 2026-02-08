<script setup lang="ts">
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

function logout() {
  const params = auth.idToken ? `?id_token_hint=${encodeURIComponent(auth.idToken)}` : ''
  window.location.href = `/auth/logout${params}`
}
</script>

<template>
  <div class="flex min-h-[60vh] items-center justify-center">
    <div class="text-center">
      <h2 class="mb-4 text-2xl font-bold text-gray-900">Access Denied</h2>
      <p class="mb-6 text-gray-600">
        You do not have permission to access this application.
        Please contact your administrator.
      </p>
      <button
        @click="logout"
        class="rounded-md bg-gray-800 px-4 py-2 text-white hover:bg-gray-700"
      >
        Log out
      </button>
    </div>
  </div>
</template>
