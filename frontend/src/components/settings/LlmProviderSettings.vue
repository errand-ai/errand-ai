<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  setDefaultProvider,
  type LlmProviderData,
} from '../../composables/useApi'

const emit = defineEmits<{
  'providers-changed': []
}>()

const providers = ref<LlmProviderData[]>([])
const loading = ref(true)
const showAddDialog = ref(false)
const showEditDialog = ref(false)
const showDeleteDialog = ref(false)
const editingProvider = ref<LlmProviderData | null>(null)
const deletingProvider = ref<LlmProviderData | null>(null)
const saving = ref(false)

// Form fields
const formName = ref('')
const formBaseUrl = ref('')
const formApiKey = ref('')

async function loadProviders() {
  loading.value = true
  try {
    providers.value = await fetchProviders()
  } catch {
    toast.error('Failed to load providers.')
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  formName.value = ''
  formBaseUrl.value = ''
  formApiKey.value = ''
  showAddDialog.value = true
}

function openEditDialog(provider: LlmProviderData) {
  editingProvider.value = provider
  formName.value = provider.name
  formBaseUrl.value = provider.base_url
  formApiKey.value = ''
  showEditDialog.value = true
}

function openDeleteDialog(provider: LlmProviderData) {
  deletingProvider.value = provider
  showDeleteDialog.value = true
}

async function handleAdd() {
  saving.value = true
  try {
    await createProvider({ name: formName.value, base_url: formBaseUrl.value, api_key: formApiKey.value })
    toast.success('Provider created.')
    showAddDialog.value = false
    await loadProviders()
    emit('providers-changed')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to create provider.')
  } finally {
    saving.value = false
  }
}

async function handleEdit() {
  if (!editingProvider.value) return
  saving.value = true
  try {
    const data: Record<string, string> = {}
    if (formName.value !== editingProvider.value.name) data.name = formName.value
    if (formBaseUrl.value !== editingProvider.value.base_url) data.base_url = formBaseUrl.value
    if (formApiKey.value) data.api_key = formApiKey.value
    await updateProvider(editingProvider.value.id, data)
    toast.success('Provider updated.')
    showEditDialog.value = false
    await loadProviders()
    emit('providers-changed')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to update provider.')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!deletingProvider.value) return
  saving.value = true
  try {
    await deleteProvider(deletingProvider.value.id)
    toast.success('Provider deleted.')
    showDeleteDialog.value = false
    await loadProviders()
    emit('providers-changed')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to delete provider.')
  } finally {
    saving.value = false
  }
}

async function handleSetDefault(provider: LlmProviderData) {
  try {
    await setDefaultProvider(provider.id)
    toast.success(`${provider.name} set as default.`)
    await loadProviders()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to set default provider.')
  }
}

function providerTypeLabel(type: string): string {
  if (type === 'litellm') return 'LiteLLM'
  if (type === 'openai_compatible') return 'OpenAI Compatible'
  return 'Unknown'
}

defineExpose({ providers, loadProviders })

onMounted(loadProviders)
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-lg font-semibold text-gray-800">LLM Providers</h3>
      <button
        @click="openAddDialog"
        class="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
      >
        Add Provider
      </button>
    </div>

    <div v-if="loading" class="text-sm text-gray-500">Loading providers...</div>
    <div v-else-if="providers.length === 0" class="text-sm text-gray-500">
      No LLM providers configured. Add one to enable AI features.
    </div>
    <table v-else class="w-full text-sm">
      <thead>
        <tr class="border-b text-left text-gray-600">
          <th class="pb-2 font-medium">Name</th>
          <th class="pb-2 font-medium">Base URL</th>
          <th class="pb-2 font-medium">Type</th>
          <th class="pb-2 font-medium">Source</th>
          <th class="pb-2 font-medium text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in providers" :key="p.id" class="border-b last:border-0">
          <td class="py-2">
            {{ p.name }}
            <span v-if="p.is_default" class="ml-1 inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">Default</span>
          </td>
          <td class="py-2 text-gray-600 truncate max-w-xs">{{ p.base_url }}</td>
          <td class="py-2 text-gray-600">{{ providerTypeLabel(p.provider_type) }}</td>
          <td class="py-2">
            <span v-if="p.source === 'env'" class="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">ENV</span>
            <span v-else class="text-gray-600">Database</span>
          </td>
          <td class="py-2 text-right space-x-2">
            <template v-if="p.source !== 'env'">
              <button @click="openEditDialog(p)" class="text-blue-600 hover:text-blue-800 text-xs">Edit</button>
              <button v-if="!p.is_default" @click="openDeleteDialog(p)" class="text-red-600 hover:text-red-800 text-xs">Delete</button>
            </template>
            <button v-if="!p.is_default" @click="handleSetDefault(p)" class="text-gray-600 hover:text-gray-800 text-xs">Set Default</button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Add Provider Dialog -->
    <div v-if="showAddDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showAddDialog = false">
      <div class="bg-white rounded-lg p-6 shadow-xl w-full max-w-md">
        <h4 class="text-lg font-semibold mb-4">Add Provider</h4>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input v-model="formName" type="text" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="e.g. OpenAI" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
            <input v-model="formBaseUrl" type="text" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="https://api.openai.com/v1" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
            <input v-model="formApiKey" type="password" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-4">
          <button @click="showAddDialog = false" class="rounded-md px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">Cancel</button>
          <button @click="handleAdd" :disabled="saving || !formName || !formBaseUrl || !formApiKey" class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {{ saving ? 'Creating...' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Edit Provider Dialog -->
    <div v-if="showEditDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showEditDialog = false">
      <div class="bg-white rounded-lg p-6 shadow-xl w-full max-w-md">
        <h4 class="text-lg font-semibold mb-4">Edit Provider</h4>
        <div class="space-y-3">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input v-model="formName" type="text" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
            <input v-model="formBaseUrl" type="text" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
            <input v-model="formApiKey" type="password" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="Leave blank to keep current key" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-4">
          <button @click="showEditDialog = false" class="rounded-md px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">Cancel</button>
          <button @click="handleEdit" :disabled="saving || !formName || !formBaseUrl" class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            {{ saving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Provider Dialog -->
    <div v-if="showDeleteDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showDeleteDialog = false">
      <div class="bg-white rounded-lg p-6 shadow-xl w-full max-w-md">
        <h4 class="text-lg font-semibold mb-2">Delete Provider</h4>
        <p class="text-sm text-gray-600 mb-4">
          Are you sure you want to delete <strong>{{ deletingProvider?.name }}</strong>?
          Any model configurations using this provider will be cleared and will need to be reconfigured.
        </p>
        <div class="flex justify-end gap-2">
          <button @click="showDeleteDialog = false" class="rounded-md px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">Cancel</button>
          <button @click="handleDelete" :disabled="saving" class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50">
            {{ saving ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
