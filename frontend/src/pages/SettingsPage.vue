<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { fetchLlmModels, saveLlmModel } from '../composables/useApi'

const auth = useAuthStore()

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'

const systemPrompt = ref('')
const mcpServers = ref<unknown>(null)
const llmModel = ref(DEFAULT_MODEL)
const llmModels = ref<string[]>([])
const llmModelsError = ref<string | null>(null)
const llmModelSaving = ref(false)
const llmModelSuccess = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref<string | null>(null)
const saveSuccess = ref(false)

async function settingsFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

async function loadSettings() {
  loading.value = true
  error.value = null
  try {
    const res = await settingsFetch('/api/settings')
    if (res.status === 403) {
      error.value = 'Access denied — admin role required.'
      return
    }
    if (!res.ok) {
      error.value = `Failed to load settings (HTTP ${res.status})`
      return
    }
    const data = await res.json()
    systemPrompt.value = data.system_prompt ?? ''
    mcpServers.value = data.mcp_servers ?? null
    llmModel.value = data.llm_model ?? DEFAULT_MODEL
  } catch {
    error.value = 'Failed to load settings. Please check your connection.'
  } finally {
    loading.value = false
  }
}

async function saveSystemPrompt() {
  saving.value = true
  error.value = null
  saveSuccess.value = false
  try {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system_prompt: systemPrompt.value }),
    })
    if (res.status === 403) {
      error.value = 'Access denied — admin role required.'
      return
    }
    if (!res.ok) {
      error.value = `Failed to save settings (HTTP ${res.status})`
      return
    }
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
  } catch {
    error.value = 'Failed to save settings. Please check your connection.'
  } finally {
    saving.value = false
  }
}

async function loadModels() {
  llmModelsError.value = null
  try {
    llmModels.value = await fetchLlmModels()
  } catch {
    llmModelsError.value = 'Failed to load available models.'
  }
}

async function onModelChange() {
  llmModelSaving.value = true
  llmModelSuccess.value = false
  try {
    await saveLlmModel(llmModel.value)
    llmModelSuccess.value = true
    setTimeout(() => { llmModelSuccess.value = false }, 3000)
  } catch {
    error.value = 'Failed to save model selection.'
  } finally {
    llmModelSaving.value = false
  }
}

onMounted(async () => {
  await loadSettings()
  await loadModels()
})
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <h2 class="text-2xl font-bold text-gray-900 mb-6">Settings</h2>

    <div v-if="error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
      {{ error }}
    </div>

    <div v-if="loading" class="text-sm text-gray-500">Loading settings...</div>

    <template v-else>
      <!-- System Prompt -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">System Prompt</h3>
        <textarea
          v-model="systemPrompt"
          rows="6"
          class="w-full rounded-md border border-gray-300 p-3 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="Enter the system prompt for the LLM..."
        ></textarea>
        <div class="mt-3 flex items-center gap-3">
          <button
            @click="saveSystemPrompt"
            :disabled="saving"
            class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {{ saving ? 'Saving...' : 'Save' }}
          </button>
          <span v-if="saveSuccess" class="text-sm text-green-600">Settings saved.</span>
        </div>
      </div>

      <!-- LLM Model -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">LLM Model</h3>
        <div v-if="llmModelsError" class="text-sm text-red-600 mb-2">{{ llmModelsError }}</div>
        <div class="flex items-center gap-3">
          <select
            v-model="llmModel"
            :disabled="llmModels.length === 0 || llmModelSaving"
            class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
            @change="onModelChange"
          >
            <option v-if="llmModels.length === 0" :value="llmModel">{{ llmModel }}</option>
            <option v-for="m in llmModels" :key="m" :value="m">{{ m }}</option>
          </select>
          <span v-if="llmModelSaving" class="text-sm text-gray-500">Saving...</span>
          <span v-if="llmModelSuccess" class="text-sm text-green-600">Model saved.</span>
        </div>
      </div>

      <!-- MCP Server Configuration -->
      <div class="rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">MCP Server Configuration</h3>
        <p class="text-sm text-gray-500 mb-3">
          MCP server configuration will be available in a future update.
        </p>
        <div v-if="mcpServers" class="rounded-md bg-gray-50 p-4">
          <pre class="text-xs text-gray-700 overflow-auto">{{ JSON.stringify(mcpServers, null, 2) }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>
