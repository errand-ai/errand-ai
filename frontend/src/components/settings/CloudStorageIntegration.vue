<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchCloudStorageStatus,
  disconnectCloudStorage,
  type CloudStorageProviderStatus,
} from '../../composables/useApi'
import { useTaskStore } from '../../stores/tasks'

interface ProviderCard {
  id: string
  label: string
  icon: string
  status: CloudStorageProviderStatus
}

const providers = ref<ProviderCard[]>([])
const loading = ref(true)
const disconnecting = ref<string | null>(null)

const PROVIDER_META: Record<string, { label: string; icon: string }> = {
  google_drive: { label: 'Google Drive', icon: '📁' },
  onedrive: { label: 'OneDrive', icon: '☁️' },
}

async function loadStatus() {
  loading.value = true
  try {
    const status = await fetchCloudStorageStatus()
    providers.value = Object.entries(status).map(([id, providerStatus]) => ({
      id,
      label: PROVIDER_META[id]?.label ?? id,
      icon: PROVIDER_META[id]?.icon ?? '📂',
      status: providerStatus,
    }))
  } catch {
    toast.error('Failed to load cloud storage status.')
  } finally {
    loading.value = false
  }
}

function connect(providerId: string) {
  window.location.href = `/api/integrations/${providerId}/authorize`
}

async function disconnect(providerId: string) {
  disconnecting.value = providerId
  try {
    await disconnectCloudStorage(providerId)
    await loadStatus()
    toast.success(`${PROVIDER_META[providerId]?.label ?? providerId} disconnected.`)
  } catch {
    toast.error(`Failed to disconnect ${PROVIDER_META[providerId]?.label ?? providerId}.`)
  } finally {
    disconnecting.value = null
  }
}

const taskStore = useTaskStore()

watch(() => taskStore.cloudStorageChanged, () => {
  loadStatus()
})

onMounted(loadStatus)
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="cloud-storage-integration">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Cloud Storage</h3>

    <div v-if="loading" class="text-sm text-gray-500">Loading...</div>

    <div v-else class="space-y-4">
      <div
        v-for="provider in providers"
        :key="provider.id"
        class="rounded-md border p-4"
        :class="provider.status.available ? 'border-gray-200' : 'border-gray-100 bg-gray-50 opacity-60'"
        :data-testid="`cloud-card-${provider.id}`"
      >
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="text-2xl">{{ provider.icon }}</span>
            <div>
              <h4 class="font-medium text-gray-800">{{ provider.label }}</h4>
              <p v-if="!provider.status.available" class="text-xs text-gray-500">
                {{ provider.status.mcp_configured
                  ? 'Configure credentials or connect to errand cloud to enable this integration'
                  : 'Not configured — MCP server URL not set' }}
              </p>
              <p
                v-else-if="provider.status.connected"
                class="text-xs text-gray-500"
                :data-testid="`cloud-user-${provider.id}`"
              >
                Connected as {{ provider.status.user_name || provider.status.user_email || 'unknown' }}
                <span v-if="provider.status.user_name && provider.status.user_email" class="text-gray-400">
                  ({{ provider.status.user_email }})
                </span>
              </p>
            </div>
          </div>

          <div>
            <button
              v-if="provider.status.available && !provider.status.connected"
              @click="connect(provider.id)"
              class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              :data-testid="`cloud-connect-${provider.id}`"
            >
              Connect
            </button>
            <button
              v-else-if="provider.status.connected"
              @click="disconnect(provider.id)"
              :disabled="disconnecting === provider.id"
              class="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
              :data-testid="`cloud-disconnect-${provider.id}`"
            >
              {{ disconnecting === provider.id ? 'Disconnecting...' : 'Disconnect' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
