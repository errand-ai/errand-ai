<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchPlatforms,
  savePlatformCredentials,
  deletePlatformCredentials,
  verifyPlatformCredentials,
  type PlatformInfo,
} from '../../composables/useApi'
import PlatformCredentialForm from './PlatformCredentialForm.vue'

const platforms = ref<PlatformInfo[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const savingId = ref<string | null>(null)
const verifyingId = ref<string | null>(null)
const disconnectTarget = ref<PlatformInfo | null>(null)
const disconnectDialogRef = ref<HTMLDialogElement | null>(null)
const disconnecting = ref(false)

async function loadPlatforms() {
  loading.value = true
  error.value = null
  try {
    platforms.value = await fetchPlatforms()
  } catch {
    error.value = 'Failed to load platforms.'
  } finally {
    loading.value = false
  }
}

async function onSaveCredentials(platform: PlatformInfo, credentials: Record<string, string>) {
  savingId.value = platform.id
  try {
    const result = await savePlatformCredentials(platform.id, credentials)
    const idx = platforms.value.findIndex(p => p.id === platform.id)
    if (idx !== -1) platforms.value[idx] = { ...platforms.value[idx], status: result.status }
    toast.success(`${platform.label} credentials saved.`)
  } catch {
    toast.error(`Failed to save ${platform.label} credentials.`)
  } finally {
    savingId.value = null
  }
}

async function onVerify(platform: PlatformInfo) {
  verifyingId.value = platform.id
  try {
    const result = await verifyPlatformCredentials(platform.id)
    const idx = platforms.value.findIndex(p => p.id === platform.id)
    if (idx !== -1) platforms.value[idx] = { ...platforms.value[idx], status: result.status, last_verified_at: result.last_verified_at }
    if (result.status === 'connected') {
      toast.success(`${platform.label} credentials verified.`)
    } else {
      toast.error(`${platform.label} verification failed.`)
    }
  } catch {
    toast.error(`Failed to verify ${platform.label} credentials.`)
  } finally {
    verifyingId.value = null
  }
}

function showDisconnectConfirm(platform: PlatformInfo) {
  disconnectTarget.value = platform
  setTimeout(() => disconnectDialogRef.value?.showModal(), 0)
}

function cancelDisconnect() {
  disconnectDialogRef.value?.close()
  disconnectTarget.value = null
}

function onDisconnectDialogClick(e: MouseEvent) {
  if (e.target === disconnectDialogRef.value) cancelDisconnect()
}

async function confirmDisconnect() {
  if (!disconnectTarget.value) return
  const platform = disconnectTarget.value
  disconnectDialogRef.value?.close()
  disconnectTarget.value = null
  disconnecting.value = true
  try {
    await deletePlatformCredentials(platform.id)
    const idx = platforms.value.findIndex(p => p.id === platform.id)
    if (idx !== -1) {
      platforms.value[idx] = { ...platforms.value[idx], status: 'disconnected', last_verified_at: null }
    }
    toast.success(`${platform.label} disconnected.`)
  } catch {
    toast.error(`Failed to disconnect ${platform.label}.`)
  } finally {
    disconnecting.value = false
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

onMounted(loadPlatforms)
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="platform-settings">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Platforms</h3>

    <div v-if="loading" class="text-sm text-gray-500">Loading platforms...</div>

    <div v-else-if="error" class="text-sm text-red-600">{{ error }}</div>

    <div v-else-if="platforms.length === 0" class="text-sm text-gray-500">
      No platforms available.
    </div>

    <div v-else class="space-y-4">
      <div
        v-for="platform in platforms"
        :key="platform.id"
        class="rounded-md border border-gray-200 p-4"
        :data-testid="`platform-card-${platform.id}`"
      >
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span
              class="inline-block h-2.5 w-2.5 rounded-full"
              :class="platform.status === 'connected' ? 'bg-green-500' : 'bg-gray-400'"
              :data-testid="`platform-status-${platform.id}`"
            ></span>
            <h4 class="font-medium text-gray-800">{{ platform.label }}</h4>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="platform.status === 'connected'"
              @click="onVerify(platform)"
              :disabled="verifyingId === platform.id"
              class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              :data-testid="`platform-verify-${platform.id}`"
            >
              {{ verifyingId === platform.id ? 'Verifying...' : 'Verify' }}
            </button>
            <button
              v-if="platform.status === 'connected'"
              @click="showDisconnectConfirm(platform)"
              :disabled="disconnecting"
              class="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
              :data-testid="`platform-disconnect-${platform.id}`"
            >
              Disconnect
            </button>
          </div>
        </div>

        <div v-if="platform.last_verified_at" class="mb-3 text-xs text-gray-500" :data-testid="`platform-verified-at-${platform.id}`">
          Last verified: {{ formatDate(platform.last_verified_at) }}
        </div>

        <div v-if="platform.capabilities?.length > 0" class="mb-3 flex flex-wrap gap-1">
          <span
            v-for="cap in platform.capabilities"
            :key="cap"
            class="inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
          >
            {{ cap }}
          </span>
        </div>

        <PlatformCredentialForm
          v-if="platform.status !== 'connected'"
          :schema="platform.credential_schema"
          :saving="savingId === platform.id"
          @save="onSaveCredentials(platform, $event)"
        />
      </div>
    </div>

    <!-- Disconnect confirmation dialog -->
    <dialog
      ref="disconnectDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelDisconnect"
      @click="onDisconnectDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Disconnect {{ disconnectTarget?.label }}?</h3>
        <p class="mb-4 text-sm text-gray-600">This will remove the stored credentials. You'll need to re-enter them to reconnect.</p>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            @click="cancelDisconnect"
            data-testid="platform-disconnect-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
            @click="confirmDisconnect"
            data-testid="platform-disconnect-confirm"
          >
            Disconnect
          </button>
        </div>
      </div>
    </dialog>
  </div>
</template>
