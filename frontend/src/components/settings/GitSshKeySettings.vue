<script setup lang="ts">
import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { useAuthStore } from '../../stores/auth'

const props = defineProps<{
  sshPublicKey: string | null
  gitSshHosts: string[]
  saveSettings: (data: Record<string, unknown>) => Promise<void>
}>()

const emit = defineEmits<{
  'update:sshPublicKey': [value: string]
  'update:gitSshHosts': [value: string[]]
}>()

const auth = useAuthStore()
const keyCopied = ref(false)
const regenerating = ref(false)
const showRegenerateDialog = ref(false)
const regenerateDialogRef = ref<HTMLDialogElement | null>(null)
const localHosts = ref([...props.gitSshHosts])
const newHost = ref('')
const hostsError = ref<string | null>(null)
const hostsSaving = ref(false)

async function sshFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

async function copyKey() {
  if (!props.sshPublicKey) return
  await navigator.clipboard.writeText(props.sshPublicKey)
  keyCopied.value = true
  toast.success('SSH public key copied.')
  setTimeout(() => { keyCopied.value = false }, 2000)
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
    const res = await sshFetch('/api/settings/regenerate-ssh-key', { method: 'POST' })
    if (!res.ok) {
      toast.error(`Failed to regenerate SSH key (HTTP ${res.status})`)
      return
    }
    const data = await res.json()
    emit('update:sshPublicKey', data.ssh_public_key)
    toast.success('SSH key regenerated.')
  } catch {
    toast.error('Failed to regenerate SSH key. Please check your connection.')
  } finally {
    regenerating.value = false
  }
}

function addHost() {
  const host = newHost.value.trim().toLowerCase()
  if (!host) return
  if (localHosts.value.includes(host)) {
    hostsError.value = `"${host}" is already in the list.`
    return
  }
  hostsError.value = null
  localHosts.value.push(host)
  newHost.value = ''
}

function removeHost(index: number) {
  localHosts.value.splice(index, 1)
}

async function saveHosts() {
  hostsSaving.value = true
  hostsError.value = null
  try {
    await props.saveSettings({ git_ssh_hosts: localHosts.value })
    emit('update:gitSshHosts', [...localHosts.value])
    toast.success('SSH hosts saved.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to save SSH hosts.')
  } finally {
    hostsSaving.value = false
  }
}
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Git SSH Key</h3>

    <div v-if="sshPublicKey" class="space-y-4">
      <!-- Public key display -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Public Key</label>
        <div class="flex items-start gap-2">
          <code class="flex-1 rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-xs font-mono break-all" data-testid="ssh-public-key">{{ sshPublicKey }}</code>
          <button
            @click="copyKey"
            class="shrink-0 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            data-testid="ssh-key-copy"
          >
            {{ keyCopied ? 'Copied!' : 'Copy' }}
          </button>
        </div>
        <p class="mt-1 text-xs text-gray-500">Add this key as a deploy key to your Git repositories. Enable write access if you want the agent to push changes.</p>
      </div>

      <!-- Regenerate -->
      <div class="flex items-center gap-3">
        <button
          @click="showRegenerateConfirm"
          :disabled="regenerating"
          class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          data-testid="ssh-key-regenerate"
        >
          {{ regenerating ? 'Regenerating...' : 'Regenerate' }}
        </button>
      </div>

      <!-- SSH hosts list -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">SSH Hosts</label>
        <p class="text-xs text-gray-500 mb-2">Git hosts that should use SSH authentication.</p>
        <div v-if="hostsError" class="mb-2 text-sm text-red-600">{{ hostsError }}</div>
        <div class="space-y-1 mb-2">
          <div v-for="(host, index) in localHosts" :key="host" class="flex items-center gap-2">
            <code class="text-sm font-mono text-gray-800">{{ host }}</code>
            <button @click="removeHost(index)" class="text-xs text-red-600 hover:text-red-800" data-testid="ssh-host-remove">Remove</button>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <input
            v-model="newHost"
            type="text"
            class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            placeholder="e.g. gitlab.com"
            @keyup.enter="addHost"
            data-testid="ssh-host-input"
          />
          <button @click="addHost" class="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50" data-testid="ssh-host-add">Add Host</button>
        </div>
        <div class="mt-3 flex items-center gap-3">
          <button
            @click="saveHosts"
            :disabled="hostsSaving"
            class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            data-testid="ssh-hosts-save"
          >
            {{ hostsSaving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <div v-else class="text-sm text-gray-500" data-testid="ssh-no-key">
      No SSH key generated. Restart the backend to auto-generate one.
    </div>

    <!-- Regenerate SSH key confirmation dialog -->
    <dialog
      ref="regenerateDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelRegenerate"
      @click="onRegenerateDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Regenerate SSH key?</h3>
        <p class="mb-4 text-sm text-gray-600">This will invalidate the current key. Deploy keys configured with the old public key will stop working.</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50" @click="cancelRegenerate" data-testid="ssh-regenerate-cancel">Cancel</button>
          <button type="button" class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700" @click="confirmRegenerate" data-testid="ssh-regenerate-confirm">Regenerate</button>
        </div>
      </div>
    </dialog>
  </div>
</template>
