<script setup lang="ts">
import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { useAuthStore } from '../../stores/auth'

const props = defineProps<{
  mcpApiKey: string | null
}>()

const emit = defineEmits<{
  'update:mcpApiKey': [value: string]
}>()

const auth = useAuthStore()
const revealed = ref(false)
const keyCopied = ref(false)
const configCopied = ref(false)
const regenerating = ref(false)
const showRegenerateDialog = ref(false)
const regenerateDialogRef = ref<HTMLDialogElement | null>(null)

async function keyFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

function mcpExampleConfig(): string {
  const host = window.location.origin
  return JSON.stringify({
    mcpServers: {
      'content-manager': {
        url: `${host}/mcp`,
        headers: {
          Authorization: `Bearer ${props.mcpApiKey || '<api-key>'}`
        }
      }
    }
  }, null, 2)
}

function mcpMaskedConfig(): string {
  const host = window.location.origin
  return JSON.stringify({
    mcpServers: {
      'content-manager': {
        url: `${host}/mcp`,
        headers: {
          Authorization: `Bearer ${'*'.repeat(32)}`
        }
      }
    }
  }, null, 2)
}

async function copyKey() {
  if (!props.mcpApiKey) return
  await navigator.clipboard.writeText(props.mcpApiKey)
  keyCopied.value = true
  toast.success('API key copied.')
  setTimeout(() => { keyCopied.value = false }, 2000)
}

async function copyConfig() {
  await navigator.clipboard.writeText(mcpExampleConfig())
  configCopied.value = true
  toast.success('Configuration copied.')
  setTimeout(() => { configCopied.value = false }, 2000)
}

function showRegenerateConfirm() {
  showRegenerateDialog.value = true
  setTimeout(() => regenerateDialogRef.value?.showModal(), 0)
}

function cancelRegenerate() {
  regenerateDialogRef.value?.close()
  showRegenerateDialog.value = false
}

function onRegenerateDialogClick(e: MouseEvent) {
  if (e.target === regenerateDialogRef.value) cancelRegenerate()
}

async function confirmRegenerate() {
  regenerateDialogRef.value?.close()
  showRegenerateDialog.value = false
  regenerating.value = true
  try {
    const res = await keyFetch('/api/settings/regenerate-mcp-key', { method: 'POST' })
    if (!res.ok) {
      toast.error(`Failed to regenerate key (HTTP ${res.status})`)
      return
    }
    const data = await res.json()
    emit('update:mcpApiKey', data.mcp_api_key)
    revealed.value = false
    toast.success('API key regenerated.')
  } catch {
    toast.error('Failed to regenerate key. Please check your connection.')
  } finally {
    regenerating.value = false
  }
}
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">MCP API Key</h3>

    <div v-if="mcpApiKey" class="space-y-4">
      <!-- Key display -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
        <div class="flex items-center gap-2">
          <code class="flex-1 rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-sm font-mono break-all">{{ revealed ? mcpApiKey : '\u2022'.repeat(32) }}</code>
          <button
            @click="revealed = !revealed"
            class="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            data-testid="mcp-key-reveal"
          >
            {{ revealed ? 'Hide' : 'Reveal' }}
          </button>
          <button
            @click="copyKey"
            class="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            data-testid="mcp-key-copy"
          >
            {{ keyCopied ? 'Copied!' : 'Copy' }}
          </button>
        </div>
      </div>

      <!-- Regenerate -->
      <div class="flex items-center gap-3">
        <button
          @click="showRegenerateConfirm"
          :disabled="regenerating"
          class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          data-testid="mcp-key-regenerate"
        >
          {{ regenerating ? 'Regenerating...' : 'Regenerate' }}
        </button>
      </div>

      <!-- Example config -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Example MCP Configuration</label>
        <pre class="rounded-md border border-gray-300 bg-gray-50 p-3 text-xs font-mono overflow-x-auto">{{ mcpMaskedConfig() }}</pre>
        <button
          @click="copyConfig"
          class="mt-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          data-testid="mcp-config-copy"
        >
          {{ configCopied ? 'Copied!' : 'Copy Configuration' }}
        </button>
      </div>
    </div>

    <div v-else class="text-sm text-gray-500">
      No API key generated. Restart the backend to auto-generate one.
    </div>

    <!-- Regenerate confirmation dialog -->
    <dialog
      ref="regenerateDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelRegenerate"
      @click="onRegenerateDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Regenerate API key?</h3>
        <p class="mb-4 text-sm text-gray-600">This will invalidate the current key. All MCP clients will need to be reconfigured.</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50" @click="cancelRegenerate" data-testid="mcp-regenerate-cancel">Cancel</button>
          <button type="button" class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700" @click="confirmRegenerate" data-testid="mcp-regenerate-confirm">Regenerate</button>
        </div>
      </div>
    </dialog>
  </div>
</template>
