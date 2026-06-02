<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchMarketplaces,
  createMarketplace,
  patchMarketplace,
  deleteMarketplace,
  resyncMarketplace,
  type Marketplace,
  type MarketplaceSourceType,
} from '../../composables/useApi'
import { formatRelativeTime } from '../../composables/useRelativeTime'

const marketplaces = ref<Marketplace[]>([])
const loading = ref(false)
const showForm = ref(false)
const editingId = ref<string | null>(null)
const resyncingIds = ref<Set<string>>(new Set())
const togglingIds = ref<Set<string>>(new Set())
const saving = ref(false)
const formError = ref<string | null>(null)

const SOURCE_TYPES: { value: MarketplaceSourceType; label: string }[] = [
  { value: 'github', label: 'GitHub (owner/repo)' },
  { value: 'git', label: 'Git URL' },
  { value: 'http', label: 'HTTP JSON' },
  { value: 'local', label: 'Local path' },
]

const formName = ref('')
const formSourceType = ref<MarketplaceSourceType>('github')
const formSourceUrl = ref('')
const formRef = ref('')
const formAuthToken = ref('')

const showDeleteDialog = ref(false)
const deleteDialogRef = ref<HTMLDialogElement | null>(null)
const pendingDeleteId = ref<string | null>(null)

const refSupported = computed(() => formSourceType.value === 'github' || formSourceType.value === 'git')

async function load() {
  loading.value = true
  try {
    const result = await fetchMarketplaces()
    marketplaces.value = Array.isArray(result) ? result : []
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to load marketplaces.')
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editingId.value = null
  formName.value = ''
  formSourceType.value = 'github'
  formSourceUrl.value = ''
  formRef.value = ''
  formAuthToken.value = ''
  formError.value = null
  showForm.value = true
}

function openEdit(m: Marketplace) {
  editingId.value = m.id
  formName.value = m.name
  formSourceType.value = m.source_type
  formSourceUrl.value = m.source_url
  formRef.value = m.ref ?? ''
  formAuthToken.value = ''  // never echo stored token; admin re-enters to change
  formError.value = null
  showForm.value = true
}

function cancelForm() {
  showForm.value = false
  editingId.value = null
  formError.value = null
}

async function submit() {
  if (!formName.value.trim()) {
    formError.value = 'Name is required.'
    return
  }
  if (!formSourceUrl.value.trim()) {
    formError.value = 'Source URL is required.'
    return
  }
  saving.value = true
  formError.value = null
  try {
    if (editingId.value) {
      const patch: Record<string, unknown> = {
        name: formName.value.trim(),
        source_url: formSourceUrl.value.trim(),
        ref: refSupported.value ? (formRef.value.trim() || null) : null,
      }
      if (formAuthToken.value) patch.auth_token = formAuthToken.value
      await patchMarketplace(editingId.value, patch)
      toast.success('Marketplace updated.')
    } else {
      await createMarketplace({
        name: formName.value.trim(),
        source_type: formSourceType.value,
        source_url: formSourceUrl.value.trim(),
        ref: refSupported.value ? (formRef.value.trim() || null) : null,
        auth_token: formAuthToken.value || null,
      })
      toast.success('Marketplace added.')
    }
    showForm.value = false
    editingId.value = null
    await load()
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Failed to save marketplace.'
    formError.value = msg
    toast.error(msg)
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(m: Marketplace) {
  togglingIds.value.add(m.id)
  try {
    const updated = await patchMarketplace(m.id, { enabled: !m.enabled })
    const idx = marketplaces.value.findIndex((row) => row.id === m.id)
    if (idx >= 0) marketplaces.value[idx] = updated
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to toggle marketplace.')
  } finally {
    togglingIds.value.delete(m.id)
  }
}

async function doResync(m: Marketplace) {
  resyncingIds.value.add(m.id)
  try {
    await resyncMarketplace(m.id)
    await load()
    toast.success('Marketplace resynced.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to resync marketplace.')
  } finally {
    resyncingIds.value.delete(m.id)
  }
}

function requestDelete(id: string) {
  pendingDeleteId.value = id
  showDeleteDialog.value = true
  setTimeout(() => deleteDialogRef.value?.showModal(), 0)
}

function cancelDelete() {
  deleteDialogRef.value?.close()
  showDeleteDialog.value = false
  pendingDeleteId.value = null
}

function onDeleteDialogClick(e: MouseEvent) {
  if (e.target === deleteDialogRef.value) cancelDelete()
}

async function confirmDelete() {
  const id = pendingDeleteId.value
  deleteDialogRef.value?.close()
  showDeleteDialog.value = false
  pendingDeleteId.value = null
  if (!id) return
  try {
    await deleteMarketplace(id)
    await load()
    toast.success('Marketplace removed.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to remove marketplace.')
  }
}

function sourceTypeLabel(value: MarketplaceSourceType): string {
  return SOURCE_TYPES.find((entry) => entry.value === value)?.label ?? value
}

onMounted(load)
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="marketplaces-section">
    <div class="flex items-center justify-between mb-3">
      <div>
        <h3 class="text-lg font-semibold text-gray-800">
          Plugin Marketplaces
          <span class="ml-2 text-sm font-normal text-gray-500">({{ marketplaces.length }})</span>
        </h3>
        <p class="text-sm text-gray-500">Sources of plugins that contribute skills and MCP servers to tasks.</p>
      </div>
    </div>

    <div v-if="loading" class="text-sm text-gray-400">Loading marketplaces...</div>

    <div v-else-if="marketplaces.length === 0 && !showForm" class="text-sm text-gray-400 mb-3" data-testid="marketplaces-empty-state">
      No marketplaces configured.
    </div>

    <div v-else-if="!showForm" class="space-y-2 mb-3">
      <div
        v-for="m in marketplaces"
        :key="m.id"
        class="rounded-md border border-gray-200 p-3"
        :data-testid="`marketplace-row-${m.id}`"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-sm font-medium text-gray-800">{{ m.name }}</span>
              <span
                v-if="m.predefined"
                class="inline-block rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700"
                data-testid="marketplace-predefined-badge"
              >Predefined</span>
              <span
                v-if="m.last_sync_status === 'error'"
                class="inline-block rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700"
                :title="m.last_sync_error || ''"
                data-testid="marketplace-sync-error"
              >Sync error</span>
              <span
                v-else-if="m.last_sync_status === 'ok'"
                class="inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700"
              >Sync ok</span>
            </div>
            <div class="text-xs text-gray-500 break-all">
              {{ sourceTypeLabel(m.source_type) }} — {{ m.source_url }}<span v-if="m.ref"> @ {{ m.ref }}</span>
            </div>
            <div class="text-xs text-gray-400 mt-1">
              <span>{{ m.plugin_count }} plugin{{ m.plugin_count === 1 ? '' : 's' }}</span>
              <span class="mx-1">·</span>
              <span v-if="m.last_synced_at">Synced {{ formatRelativeTime(m.last_synced_at) }}</span>
              <span v-else>Never synced</span>
            </div>
            <div v-if="m.last_sync_status === 'error' && m.last_sync_error" class="mt-1 text-xs text-red-600" data-testid="marketplace-sync-error-message">
              {{ m.last_sync_error }}
            </div>
          </div>

          <div class="flex items-center gap-3 shrink-0">
            <label class="flex items-center gap-1.5 text-xs text-gray-600">
              <input
                type="checkbox"
                :checked="m.enabled"
                :disabled="togglingIds.has(m.id)"
                @change="toggleEnabled(m)"
                class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                :data-testid="`marketplace-toggle-${m.id}`"
              />
              Enabled
            </label>
            <button
              @click="doResync(m)"
              :disabled="resyncingIds.has(m.id)"
              class="text-xs text-blue-600 hover:text-blue-800 disabled:opacity-50"
              :data-testid="`marketplace-resync-${m.id}`"
            >
              {{ resyncingIds.has(m.id) ? 'Resyncing...' : 'Resync' }}
            </button>
            <button
              @click="openEdit(m)"
              class="text-xs text-blue-600 hover:text-blue-800"
              :data-testid="`marketplace-edit-${m.id}`"
            >
              Edit
            </button>
            <button
              @click="requestDelete(m.id)"
              :disabled="m.predefined"
              :title="m.predefined ? 'Predefined marketplaces cannot be removed' : ''"
              class="text-xs text-red-600 hover:text-red-800 disabled:opacity-50 disabled:cursor-not-allowed"
              :data-testid="`marketplace-delete-${m.id}`"
            >
              Remove
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showForm" class="rounded-md border border-gray-200 p-4 mb-3 space-y-3" data-testid="marketplace-form">
      <h4 class="text-sm font-semibold text-gray-700">{{ editingId ? 'Edit Marketplace' : 'Add Marketplace' }}</h4>
      <div v-if="formError" class="text-sm text-red-600" data-testid="marketplace-form-error">{{ formError }}</div>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Name</label>
        <input
          v-model="formName"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="e.g. acme-public"
          data-testid="marketplace-name-input"
        />
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Source type</label>
        <div class="flex flex-wrap gap-3" data-testid="marketplace-source-type">
          <label
            v-for="opt in SOURCE_TYPES"
            :key="opt.value"
            class="flex items-center gap-1.5 text-xs text-gray-600"
          >
            <input
              type="radio"
              :value="opt.value"
              v-model="formSourceType"
              :disabled="!!editingId"
              class="text-blue-600"
              :data-testid="`marketplace-source-${opt.value}`"
            />
            {{ opt.label }}
          </label>
        </div>
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Source URL</label>
        <input
          v-model="formSourceUrl"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          :placeholder="formSourceType === 'github' ? 'owner/repo' : formSourceType === 'http' ? 'https://example.com/marketplace.json' : formSourceType === 'local' ? '/path/to/marketplace.json' : 'https://...'"
          data-testid="marketplace-source-url-input"
        />
      </div>
      <div v-if="refSupported">
        <label class="block text-xs font-medium text-gray-600 mb-1">Ref (optional)</label>
        <input
          v-model="formRef"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="main, v1.2.0, ..."
          data-testid="marketplace-ref-input"
        />
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Bearer token (optional)</label>
        <input
          v-model="formAuthToken"
          type="password"
          autocomplete="off"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          :placeholder="editingId ? 'Leave blank to keep existing token' : 'Optional Authorization: Bearer header'"
          data-testid="marketplace-auth-token-input"
        />
      </div>
      <div class="flex gap-2">
        <button
          @click="submit"
          :disabled="saving"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          data-testid="marketplace-save"
        >
          {{ saving ? 'Saving...' : (editingId ? 'Update' : 'Add') }}
        </button>
        <button
          @click="cancelForm"
          class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          data-testid="marketplace-cancel"
        >
          Cancel
        </button>
      </div>
    </div>

    <button
      v-if="!showForm"
      @click="openAdd"
      class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
      data-testid="marketplace-add"
    >
      Add Marketplace
    </button>

    <dialog
      ref="deleteDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelDelete"
      @click="onDeleteDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Remove marketplace?</h3>
        <p class="mb-4 text-sm text-gray-600">Plugins already installed from this marketplace remain installed, but new installs from it become unavailable.</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50" @click="cancelDelete" data-testid="marketplace-delete-cancel">Cancel</button>
          <button type="button" class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700" @click="confirmDelete" data-testid="marketplace-delete-confirm">Remove</button>
        </div>
      </div>
    </dialog>
  </div>
</template>
