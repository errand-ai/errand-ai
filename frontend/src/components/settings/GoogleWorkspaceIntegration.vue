<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchCloudStorageStatus,
  authorizeCloudStorage,
  disconnectCloudStorage,
  type CloudStorageProviderStatus,
} from '../../composables/useApi'
import { useTaskStore } from '../../stores/tasks'

const PROVIDER_ID = 'google_drive'

interface Service {
  key: string
  label: string
  icon: string
}

const SERVICES: Service[] = [
  { key: 'drive', label: 'Drive', icon: '📁' },
  { key: 'gmail', label: 'Gmail', icon: '📧' },
  { key: 'calendar', label: 'Calendar', icon: '📅' },
  { key: 'sheets', label: 'Sheets', icon: '📊' },
  { key: 'docs', label: 'Docs', icon: '📄' },
  { key: 'chat', label: 'Chat', icon: '💬' },
  { key: 'tasks', label: 'Tasks', icon: '✅' },
  { key: 'contacts', label: 'Contacts', icon: '👥' },
]

const status = ref<CloudStorageProviderStatus | null>(null)
const loading = ref(true)
const disconnecting = ref(false)

// Polling state for the OAuth popup. Tracked in refs so the interval is
// cleared deterministically on unmount or after a max wait — we don't want a
// stray timer running forever if the popup is blocked or the user navigates
// away mid-flow.
const popupPoll = ref<ReturnType<typeof setInterval> | null>(null)
const popupTimeout = ref<ReturnType<typeof setTimeout> | null>(null)
// Cap the popup wait at 10 minutes — beyond that, OAuth state has expired
// server-side anyway (OAUTH_STATE_TTL = 600s).
const POPUP_MAX_WAIT_MS = 10 * 60 * 1000

function stopPolling() {
  if (popupPoll.value !== null) {
    clearInterval(popupPoll.value)
    popupPoll.value = null
  }
  if (popupTimeout.value !== null) {
    clearTimeout(popupTimeout.value)
    popupTimeout.value = null
  }
}

const reauthRequired = computed(() => status.value?.reauth_required === true)
const isConnected = computed(() => status.value?.connected === true)
const isAvailable = computed(() => status.value?.available === true)

async function loadStatus() {
  loading.value = true
  try {
    const all = await fetchCloudStorageStatus()
    status.value = all[PROVIDER_ID] ?? null
  } catch {
    toast.error('Failed to load Google Workspace status.')
    status.value = null
  } finally {
    loading.value = false
  }
}

async function connect() {
  // Always clear any prior poller up-front, so blocked-popup retries (and
  // network failures during authorize) don't leave a stale interval running.
  stopPolling()
  try {
    const data = await authorizeCloudStorage(PROVIDER_ID)
    const w = 500, h = 600
    const left = window.screenX + (window.outerWidth - w) / 2
    const top = window.screenY + (window.outerHeight - h) / 2
    const popup = window.open(
      data.redirect_url,
      'google-workspace-auth',
      `width=${w},height=${h},left=${left},top=${top}`,
    )
    if (!popup) {
      toast.error('Popup blocked — please allow popups for this site')
      return
    }
    popupPoll.value = setInterval(() => {
      if (popup.closed) {
        stopPolling()
        loadStatus()
      }
    }, 500)
    popupTimeout.value = setTimeout(() => {
      // Give up polling after the max wait — OAuth state has expired server
      // side and the user can simply click Connect again.
      stopPolling()
    }, POPUP_MAX_WAIT_MS)
  } catch {
    toast.error('Failed to start Google Workspace authorization')
  }
}

async function disconnect() {
  disconnecting.value = true
  try {
    await disconnectCloudStorage(PROVIDER_ID)
    await loadStatus()
    toast.success('Google Workspace disconnected.')
  } catch {
    toast.error('Failed to disconnect Google Workspace.')
  } finally {
    disconnecting.value = false
  }
}

const taskStore = useTaskStore()
watch(() => taskStore.cloudStorageChanged, () => { loadStatus() })

onMounted(loadStatus)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="google-workspace-integration">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Google Workspace</h3>

    <div v-if="loading" class="text-sm text-gray-500">Loading...</div>

    <div v-else-if="!status" class="text-sm text-red-600">Failed to load status.</div>

    <div v-else>
      <div
        class="rounded-md border p-4"
        :class="isAvailable ? 'border-gray-200' : 'border-gray-100 bg-gray-50 opacity-60'"
      >
        <div class="flex items-start justify-between">
          <div class="flex items-start gap-3">
            <span class="text-2xl">🟢</span>
            <div>
              <h4 class="font-medium text-gray-800">Google Workspace</h4>
              <p v-if="!isAvailable" class="text-xs text-gray-500">
                Configure Google credentials or connect to errand cloud to enable this integration
              </p>
              <p
                v-else-if="isConnected"
                class="text-xs text-gray-500"
                data-testid="google-workspace-user"
              >
                Connected as {{ status.user_name || status.user_email || 'unknown' }}
                <span v-if="status.user_name && status.user_email" class="text-gray-400">
                  ({{ status.user_email }})
                </span>
              </p>
              <p v-else class="text-xs text-gray-500">
                Connect to give agents access to Drive, Gmail, Calendar, and more
              </p>

              <p
                v-if="reauthRequired"
                class="mt-2 text-xs text-amber-700"
                data-testid="google-workspace-reauth-warning"
              >
                Expanded permissions are required — please re-authorize to enable additional
                Google Workspace services.
              </p>
            </div>
          </div>

          <div>
            <button
              v-if="isAvailable && !isConnected"
              @click="connect"
              class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              data-testid="google-workspace-connect"
            >
              Connect
            </button>
            <button
              v-else-if="isConnected && reauthRequired"
              @click="connect"
              class="rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
              data-testid="google-workspace-reauthorize"
            >
              Re-authorize
            </button>
            <button
              v-else-if="isConnected"
              @click="disconnect"
              :disabled="disconnecting"
              class="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
              data-testid="google-workspace-disconnect"
            >
              {{ disconnecting ? 'Disconnecting...' : 'Disconnect' }}
            </button>
          </div>
        </div>

        <div class="mt-4 flex flex-wrap gap-2" data-testid="google-workspace-services">
          <span
            v-for="svc in SERVICES"
            :key="svc.key"
            class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs"
            :class="isConnected && !reauthRequired
              ? 'border-blue-200 bg-blue-50 text-blue-700'
              : 'border-gray-200 bg-gray-50 text-gray-400'"
            :data-testid="`google-service-${svc.key}`"
          >
            <span aria-hidden="true">{{ svc.icon }}</span>
            {{ svc.label }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
