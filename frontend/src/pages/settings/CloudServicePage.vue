<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const route = useRoute()

interface CloudEndpoint {
  integration: string
  endpoint_type: string
  url: string
  token: string
}

interface CloudStatus {
  status: 'not_configured' | 'connected' | 'error'
  tenant_id?: string
  endpoints?: CloudEndpoint[]
  slack_configured?: boolean
  detail?: string
}

const cloudStatus = ref<CloudStatus>({ status: 'not_configured' })
const loading = ref(true)
const disconnecting = ref(false)

const isConnected = computed(() => cloudStatus.value.status === 'connected')
const isError = computed(() => cloudStatus.value.status === 'error')
const isNotConfigured = computed(() => cloudStatus.value.status === 'not_configured')
const hasEndpoints = computed(() => (cloudStatus.value.endpoints?.length ?? 0) > 0)

async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

async function fetchStatus() {
  loading.value = true
  try {
    const resp = await apiFetch('/api/cloud/status')
    if (resp.ok) {
      cloudStatus.value = await resp.json()
    }
  } catch {
    // Silent failure — status display is best-effort
  } finally {
    loading.value = false
  }
}

function handleConnect() {
  // Full page navigation to initiate OAuth flow
  window.location.href = '/api/cloud/auth/login'
}

async function handleDisconnect() {
  disconnecting.value = true
  try {
    const resp = await apiFetch('/api/cloud/auth/disconnect', { method: 'POST' })
    if (resp.ok) {
      toast.success('Disconnected from Errand Cloud')
      await fetchStatus()
    } else {
      toast.error('Failed to disconnect')
    }
  } catch {
    toast.error('Failed to disconnect')
  } finally {
    disconnecting.value = false
  }
}

function handleReconnect() {
  handleConnect()
}

async function copyUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url)
    toast.success('URL copied to clipboard')
  } catch {
    toast.error('Failed to copy URL')
  }
}

onMounted(async () => {
  // Handle error from OAuth callback redirect
  const error = route.query.error as string | undefined
  if (error) {
    toast.error(error)
  }
  await fetchStatus()
})
</script>

<template>
  <div class="space-y-6">
    <div class="rounded-lg bg-white p-6 shadow">
      <h3 class="text-lg font-semibold text-gray-900 mb-1">Cloud Service</h3>
      <p class="text-sm text-gray-500 mb-6">
        Connect your instance to Errand Cloud to receive webhooks without configuring port forwarding.
      </p>

      <!-- Loading state -->
      <div v-if="loading" class="space-y-3">
        <div class="h-4 w-48 rounded bg-gray-200 animate-pulse"></div>
        <div class="h-4 w-32 rounded bg-gray-200 animate-pulse"></div>
      </div>

      <!-- Not configured -->
      <div v-else-if="isNotConfigured" data-testid="cloud-not-connected">
        <button
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          data-testid="cloud-connect-btn"
          @click="handleConnect"
        >
          Connect to Errand Cloud
        </button>
      </div>

      <!-- Connected -->
      <div v-else-if="isConnected" data-testid="cloud-connected">
        <div class="flex items-center gap-2 mb-4">
          <span class="inline-block h-2.5 w-2.5 rounded-full bg-green-500"></span>
          <span class="text-sm font-medium text-green-700">Connected</span>
          <span v-if="cloudStatus.tenant_id" class="text-xs text-gray-400 ml-2">
            {{ cloudStatus.tenant_id }}
          </span>
        </div>
        <button
          class="rounded-md bg-red-50 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100"
          data-testid="cloud-disconnect-btn"
          :disabled="disconnecting"
          @click="handleDisconnect"
        >
          {{ disconnecting ? 'Disconnecting...' : 'Disconnect' }}
        </button>
      </div>

      <!-- Error -->
      <div v-else-if="isError" data-testid="cloud-error">
        <div class="flex items-center gap-2 mb-2">
          <span class="inline-block h-2.5 w-2.5 rounded-full bg-red-500"></span>
          <span class="text-sm font-medium text-red-700">Error</span>
        </div>
        <p v-if="cloudStatus.detail" class="text-sm text-red-600 mb-4">{{ cloudStatus.detail }}</p>
        <button
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          data-testid="cloud-reconnect-btn"
          @click="handleReconnect"
        >
          Reconnect
        </button>
      </div>
    </div>

    <!-- Cloud Endpoints -->
    <div v-if="isConnected" class="rounded-lg bg-white p-6 shadow">
      <h3 class="text-lg font-semibold text-gray-900 mb-1">Cloud Endpoints</h3>

      <div v-if="hasEndpoints" class="space-y-3 mt-4" data-testid="cloud-endpoints">
        <div
          v-for="ep in cloudStatus.endpoints"
          :key="ep.token"
          class="flex items-center justify-between rounded-md border border-gray-200 px-4 py-3"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-gray-500 uppercase">{{ ep.integration }}</span>
              <span class="text-xs text-gray-400">/</span>
              <span class="text-xs font-medium text-gray-500">{{ ep.endpoint_type }}</span>
            </div>
            <p class="mt-1 truncate text-sm font-mono text-gray-700">{{ ep.url }}</p>
          </div>
          <button
            class="ml-4 rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200"
            data-testid="copy-endpoint-btn"
            @click="copyUrl(ep.url)"
          >
            Copy
          </button>
        </div>
      </div>

      <p v-else-if="cloudStatus.slack_configured" class="text-sm text-gray-500 mt-4" data-testid="cloud-registering">
        Endpoints are being registered with Errand Cloud...
      </p>

      <p v-else class="text-sm text-gray-500 mt-4" data-testid="cloud-no-slack">
        Enable Slack in Integrations to configure cloud webhook endpoints.
      </p>
    </div>
  </div>
</template>
