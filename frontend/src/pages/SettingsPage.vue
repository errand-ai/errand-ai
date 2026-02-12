<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { fetchLlmModels, saveLlmModel, saveTaskProcessingModel, fetchTranscriptionModels, saveTranscriptionModel } from '../composables/useApi'

const auth = useAuthStore()

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'
const DEFAULT_TASK_PROCESSING_MODEL = 'claude-sonnet-4-5-20250929'

const systemPrompt = ref('')
const mcpServersText = ref('')
const mcpExpanded = ref(false)
const mcpError = ref<string | null>(null)
const mcpSaving = ref(false)
const mcpSuccess = ref(false)
const llmModel = ref(DEFAULT_MODEL)
const llmModels = ref<string[]>([])
const llmModelsError = ref<string | null>(null)
const llmModelSaving = ref(false)
const llmModelSuccess = ref(false)
const taskProcessingModel = ref(DEFAULT_TASK_PROCESSING_MODEL)
const taskProcessingModelSaving = ref(false)
const taskProcessingModelSuccess = ref(false)
const transcriptionModel = ref<string>('')
const transcriptionModels = ref<string[]>([])
const transcriptionModelsError = ref<string | null>(null)
const transcriptionModelSaving = ref(false)
const transcriptionModelSuccess = ref(false)
const timezoneValue = ref('UTC')
const timezoneSaving = ref(false)
const timezoneSuccess = ref(false)
const timezones = ref<string[]>([])
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
    mcpServersText.value = data.mcp_servers ? JSON.stringify(data.mcp_servers, null, 2) : ''
    llmModel.value = data.llm_model ?? DEFAULT_MODEL
    taskProcessingModel.value = data.task_processing_model ?? DEFAULT_TASK_PROCESSING_MODEL
    transcriptionModel.value = data.transcription_model ?? ''
    timezoneValue.value = data.timezone ?? 'UTC'
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

function validateMcpConfig(parsed: unknown): string | null {
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return 'MCP configuration must be a JSON object.'
  }

  const config = parsed as Record<string, unknown>
  const servers = config.mcpServers
  if (servers === undefined) {
    // Allow empty object with no mcpServers key
    if (Object.keys(config).length === 0) return null
    return 'MCP configuration must have a "mcpServers" key.'
  }

  if (typeof servers !== 'object' || servers === null || Array.isArray(servers)) {
    return '"mcpServers" must be an object mapping server names to configurations.'
  }

  const serverEntries = servers as Record<string, unknown>
  for (const [name, entry] of Object.entries(serverEntries)) {
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
      return `Server '${name}' must be an object with a 'url' field.`
    }

    const serverEntry = entry as Record<string, unknown>

    // Reject STDIO pattern
    if ('command' in serverEntry || 'args' in serverEntry) {
      return `Only HTTP Streaming MCP servers are supported. Server '${name}' uses STDIO transport (command/args) which is not allowed.`
    }

    // Require url field
    if (!('url' in serverEntry) || typeof serverEntry.url !== 'string' || !serverEntry.url) {
      return `Server '${name}' is missing required 'url' field.`
    }
  }

  return null
}

async function saveMcpServers() {
  mcpError.value = null
  mcpSuccess.value = false

  // Validate JSON
  let parsed: unknown
  const trimmed = mcpServersText.value.trim()
  if (trimmed === '') {
    parsed = {}
  } else {
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      mcpError.value = 'Invalid JSON. Please check syntax and try again.'
      return
    }
  }

  // Validate MCP config structure
  const validationError = validateMcpConfig(parsed)
  if (validationError) {
    mcpError.value = validationError
    return
  }

  mcpSaving.value = true
  try {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mcp_servers: parsed }),
    })
    if (res.status === 403) {
      mcpError.value = 'Access denied — admin role required.'
      return
    }
    if (!res.ok) {
      mcpError.value = `Failed to save MCP configuration (HTTP ${res.status})`
      return
    }
    mcpSuccess.value = true
    setTimeout(() => { mcpSuccess.value = false }, 3000)
  } catch {
    mcpError.value = 'Failed to save MCP configuration. Please check your connection.'
  } finally {
    mcpSaving.value = false
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

async function onTaskProcessingModelChange() {
  taskProcessingModelSaving.value = true
  taskProcessingModelSuccess.value = false
  try {
    await saveTaskProcessingModel(taskProcessingModel.value)
    taskProcessingModelSuccess.value = true
    setTimeout(() => { taskProcessingModelSuccess.value = false }, 3000)
  } catch {
    error.value = 'Failed to save task processing model selection.'
  } finally {
    taskProcessingModelSaving.value = false
  }
}

async function loadTranscriptionModels() {
  transcriptionModelsError.value = null
  try {
    transcriptionModels.value = await fetchTranscriptionModels()
  } catch {
    transcriptionModelsError.value = 'Failed to load transcription models.'
  }
}

async function onTranscriptionModelChange() {
  transcriptionModelSaving.value = true
  transcriptionModelSuccess.value = false
  try {
    const value = transcriptionModel.value || null
    await saveTranscriptionModel(value)
    transcriptionModelSuccess.value = true
    setTimeout(() => { transcriptionModelSuccess.value = false }, 3000)
  } catch {
    error.value = 'Failed to save transcription model selection.'
  } finally {
    transcriptionModelSaving.value = false
  }
}

async function onTimezoneChange() {
  timezoneSaving.value = true
  timezoneSuccess.value = false
  try {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timezone: timezoneValue.value }),
    })
    if (!res.ok) {
      error.value = `Failed to save timezone (HTTP ${res.status})`
      return
    }
    timezoneSuccess.value = true
    setTimeout(() => { timezoneSuccess.value = false }, 3000)
  } catch {
    error.value = 'Failed to save timezone. Please check your connection.'
  } finally {
    timezoneSaving.value = false
  }
}

onMounted(async () => {
  try {
    const zones = Intl.supportedValuesOf('timeZone')
    timezones.value = zones.includes('UTC') ? zones : ['UTC', ...zones]
  } catch {
    timezones.value = ['UTC']
  }
  await loadSettings()
  await loadModels()
  await loadTranscriptionModels()
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

      <!-- LLM Models -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">LLM Models</h3>
        <div v-if="llmModelsError" class="text-sm text-red-600 mb-2">{{ llmModelsError }}</div>

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Title Generation Model</label>
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

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Task Processing Model</label>
          <div class="flex items-center gap-3">
            <select
              v-model="taskProcessingModel"
              :disabled="llmModels.length === 0 || taskProcessingModelSaving"
              class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              @change="onTaskProcessingModelChange"
            >
              <option v-if="llmModels.length === 0" :value="taskProcessingModel">{{ taskProcessingModel }}</option>
              <option v-for="m in llmModels" :key="m" :value="m">{{ m }}</option>
            </select>
            <span v-if="taskProcessingModelSaving" class="text-sm text-gray-500">Saving...</span>
            <span v-if="taskProcessingModelSuccess" class="text-sm text-green-600">Model saved.</span>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Transcription Model</label>
          <div v-if="transcriptionModelsError" class="text-sm text-red-600 mb-1">{{ transcriptionModelsError }}</div>
          <div class="flex items-center gap-3">
            <select
              v-model="transcriptionModel"
              :disabled="(transcriptionModels.length === 0 && !transcriptionModel) || transcriptionModelSaving || !!transcriptionModelsError"
              class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              @change="onTranscriptionModelChange"
              data-testid="transcription-model-select"
            >
              <option value="">{{ transcriptionModels.length === 0 && !transcriptionModelsError ? 'No transcription models available' : 'Select a model to enable voice input' }}</option>
              <option v-for="m in transcriptionModels" :key="m" :value="m">{{ m }}</option>
            </select>
            <span v-if="transcriptionModelSaving" class="text-sm text-gray-500">Saving...</span>
            <span v-if="transcriptionModelSuccess" class="text-sm text-green-600">Model saved.</span>
          </div>
        </div>
      </div>

      <!-- Timezone -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">Timezone</h3>
        <div class="flex items-center gap-3">
          <select
            v-model="timezoneValue"
            :disabled="timezoneSaving"
            class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
            @change="onTimezoneChange"
          >
            <option v-for="tz in timezones" :key="tz" :value="tz">{{ tz }}</option>
          </select>
          <span v-if="timezoneSaving" class="text-sm text-gray-500">Saving...</span>
          <span v-if="timezoneSuccess" class="text-sm text-green-600">Timezone saved.</span>
        </div>
      </div>

      <!-- MCP Server Configuration -->
      <div class="rounded-lg bg-white p-6 shadow">
        <button
          @click="mcpExpanded = !mcpExpanded"
          class="flex w-full items-center justify-between text-left"
        >
          <h3 class="text-lg font-semibold text-gray-800">MCP Server Configuration</h3>
          <svg
            :class="{ 'rotate-180': mcpExpanded }"
            class="h-5 w-5 text-gray-500 transition-transform"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        <div v-if="mcpExpanded" class="mt-3">
          <div v-if="mcpError" class="mb-2 text-sm text-red-600">{{ mcpError }}</div>
          <textarea
            v-model="mcpServersText"
            rows="10"
            class="w-full rounded-md border border-gray-300 p-3 font-mono text-xs focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            placeholder='{"servers": []}'
          ></textarea>
          <div class="mt-3 flex items-center gap-3">
            <button
              @click="saveMcpServers"
              :disabled="mcpSaving"
              class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {{ mcpSaving ? 'Saving...' : 'Save MCP Config' }}
            </button>
            <span v-if="mcpSuccess" class="text-sm text-green-600">MCP configuration saved.</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
