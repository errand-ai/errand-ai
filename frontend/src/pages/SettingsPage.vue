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
const taskRunnerLogLevel = ref('INFO')
const taskRunnerLogLevelSaving = ref(false)
const taskRunnerLogLevelSuccess = ref(false)
const timezoneValue = ref('UTC')
const timezoneSaving = ref(false)
const timezoneSuccess = ref(false)
const timezones = ref<string[]>([])
const archiveAfterDays = ref(3)
const archiveSaving = ref(false)
const archiveSuccess = ref(false)
const mcpApiKey = ref<string | null>(null)
const mcpApiKeyRevealed = ref(false)
const mcpApiKeyCopied = ref(false)
const mcpConfigCopied = ref(false)
const mcpKeyRegenerating = ref(false)
const mcpKeyRegenerateSuccess = ref(false)
const mcpKeyRegenerateError = ref<string | null>(null)
const showRegenerateDialog = ref(false)
const regenerateDialogRef = ref<HTMLDialogElement | null>(null)
// SSH key state
const sshPublicKey = ref<string | null>(null)
const sshKeyCopied = ref(false)
const sshKeyRegenerating = ref(false)
const sshKeyRegenerateSuccess = ref(false)
const sshKeyRegenerateError = ref<string | null>(null)
const showSshRegenerateDialog = ref(false)
const sshRegenerateDialogRef = ref<HTMLDialogElement | null>(null)
const gitSshHosts = ref<string[]>([])
const newSshHost = ref('')
const sshHostsError = ref<string | null>(null)
const sshHostsSaving = ref(false)
const sshHostsSuccess = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref<string | null>(null)
const saveSuccess = ref(false)

// Skills state
interface Skill {
  id: string
  name: string
  description: string
  instructions: string
}
const skills = ref<Skill[]>([])
const skillsExpanded = ref(false)
const skillsSaving = ref(false)
const skillsSuccess = ref(false)
const skillsError = ref<string | null>(null)
const showSkillForm = ref(false)
const editingSkillId = ref<string | null>(null)
const skillForm = ref({ name: '', description: '', instructions: '' })
const skillNameError = ref<string | null>(null)

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
    mcpApiKey.value = data.mcp_api_key ?? null
    sshPublicKey.value = data.ssh_public_key ?? null
    gitSshHosts.value = Array.isArray(data.git_ssh_hosts) ? data.git_ssh_hosts : ['github.com', 'bitbucket.org']
    llmModel.value = data.llm_model ?? DEFAULT_MODEL
    taskProcessingModel.value = data.task_processing_model ?? DEFAULT_TASK_PROCESSING_MODEL
    transcriptionModel.value = data.transcription_model ?? ''
    taskRunnerLogLevel.value = data.task_runner_log_level || 'INFO'
    timezoneValue.value = data.timezone ?? 'UTC'
    archiveAfterDays.value = data.archive_after_days ?? 3
    skills.value = Array.isArray(data.skills) ? data.skills : []
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

async function saveArchiveAfterDays() {
  archiveSaving.value = true
  archiveSuccess.value = false
  try {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archive_after_days: archiveAfterDays.value }),
    })
    if (res.status === 403) {
      error.value = 'Access denied — admin role required.'
      return
    }
    if (!res.ok) {
      error.value = `Failed to save archive setting (HTTP ${res.status})`
      return
    }
    archiveSuccess.value = true
    setTimeout(() => { archiveSuccess.value = false }, 3000)
  } catch {
    error.value = 'Failed to save archive setting. Please check your connection.'
  } finally {
    archiveSaving.value = false
  }
}

function mcpExampleConfig(): string {
  const host = window.location.origin
  return JSON.stringify({
    mcpServers: {
      'content-manager': {
        url: `${host}/mcp`,
        headers: {
          Authorization: `Bearer ${mcpApiKey.value || '<api-key>'}`
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

async function copyMcpApiKey() {
  if (!mcpApiKey.value) return
  await navigator.clipboard.writeText(mcpApiKey.value)
  mcpApiKeyCopied.value = true
  setTimeout(() => { mcpApiKeyCopied.value = false }, 2000)
}

async function copyMcpConfig() {
  await navigator.clipboard.writeText(mcpExampleConfig())
  mcpConfigCopied.value = true
  setTimeout(() => { mcpConfigCopied.value = false }, 2000)
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
  mcpKeyRegenerating.value = true
  mcpKeyRegenerateError.value = null
  mcpKeyRegenerateSuccess.value = false
  try {
    const res = await settingsFetch('/api/settings/regenerate-mcp-key', { method: 'POST' })
    if (!res.ok) {
      mcpKeyRegenerateError.value = `Failed to regenerate key (HTTP ${res.status})`
      return
    }
    const data = await res.json()
    mcpApiKey.value = data.mcp_api_key
    mcpApiKeyRevealed.value = false
    mcpKeyRegenerateSuccess.value = true
    setTimeout(() => { mcpKeyRegenerateSuccess.value = false }, 3000)
  } catch {
    mcpKeyRegenerateError.value = 'Failed to regenerate key. Please check your connection.'
  } finally {
    mcpKeyRegenerating.value = false
  }
}

async function copySshPublicKey() {
  if (!sshPublicKey.value) return
  await navigator.clipboard.writeText(sshPublicKey.value)
  sshKeyCopied.value = true
  setTimeout(() => { sshKeyCopied.value = false }, 2000)
}

function showSshRegenerateConfirm() {
  showSshRegenerateDialog.value = true
  setTimeout(() => sshRegenerateDialogRef.value?.showModal(), 0)
}

function cancelSshRegenerate() {
  sshRegenerateDialogRef.value?.close()
  showSshRegenerateDialog.value = false
}

function onSshRegenerateDialogClick(e: MouseEvent) {
  if (e.target === sshRegenerateDialogRef.value) cancelSshRegenerate()
}

async function confirmSshRegenerate() {
  sshRegenerateDialogRef.value?.close()
  showSshRegenerateDialog.value = false
  sshKeyRegenerating.value = true
  sshKeyRegenerateError.value = null
  sshKeyRegenerateSuccess.value = false
  try {
    const res = await settingsFetch('/api/settings/regenerate-ssh-key', { method: 'POST' })
    if (!res.ok) {
      sshKeyRegenerateError.value = `Failed to regenerate SSH key (HTTP ${res.status})`
      return
    }
    const data = await res.json()
    sshPublicKey.value = data.ssh_public_key
    sshKeyRegenerateSuccess.value = true
    setTimeout(() => { sshKeyRegenerateSuccess.value = false }, 3000)
  } catch {
    sshKeyRegenerateError.value = 'Failed to regenerate SSH key. Please check your connection.'
  } finally {
    sshKeyRegenerating.value = false
  }
}

function addSshHost() {
  const host = newSshHost.value.trim().toLowerCase()
  if (!host) return
  if (gitSshHosts.value.includes(host)) {
    sshHostsError.value = `"${host}" is already in the list.`
    return
  }
  sshHostsError.value = null
  gitSshHosts.value.push(host)
  newSshHost.value = ''
}

function removeSshHost(index: number) {
  gitSshHosts.value.splice(index, 1)
}

async function saveSshHosts() {
  sshHostsSaving.value = true
  sshHostsSuccess.value = false
  sshHostsError.value = null
  try {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ git_ssh_hosts: gitSshHosts.value }),
    })
    if (!res.ok) {
      sshHostsError.value = `Failed to save SSH hosts (HTTP ${res.status})`
      return
    }
    sshHostsSuccess.value = true
    setTimeout(() => { sshHostsSuccess.value = false }, 3000)
  } catch {
    sshHostsError.value = 'Failed to save SSH hosts. Please check your connection.'
  } finally {
    sshHostsSaving.value = false
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

async function onTaskRunnerLogLevelChange() {
  taskRunnerLogLevelSaving.value = true
  taskRunnerLogLevelSuccess.value = false
  try {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_runner_log_level: taskRunnerLogLevel.value }),
    })
    if (!res.ok) {
      error.value = `Failed to save log level (HTTP ${res.status})`
      return
    }
    taskRunnerLogLevelSuccess.value = true
    setTimeout(() => { taskRunnerLogLevelSuccess.value = false }, 3000)
  } catch {
    error.value = 'Failed to save log level. Please check your connection.'
  } finally {
    taskRunnerLogLevelSaving.value = false
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

function openAddSkill() {
  editingSkillId.value = null
  skillForm.value = { name: '', description: '', instructions: '' }
  skillNameError.value = null
  showSkillForm.value = true
}

function openEditSkill(skill: Skill) {
  editingSkillId.value = skill.id
  skillForm.value = { name: skill.name, description: skill.description, instructions: skill.instructions }
  skillNameError.value = null
  showSkillForm.value = true
}

function cancelSkillForm() {
  showSkillForm.value = false
  editingSkillId.value = null
  skillNameError.value = null
}

async function saveSkills(updatedSkills: Skill[]) {
  skillsSaving.value = true
  skillsSuccess.value = false
  skillsError.value = null
  try {
    const res = await settingsFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skills: updatedSkills }),
    })
    if (!res.ok) {
      skillsError.value = `Failed to save skills (HTTP ${res.status})`
      return
    }
    skills.value = updatedSkills
    skillsSuccess.value = true
    setTimeout(() => { skillsSuccess.value = false }, 3000)
  } catch {
    skillsError.value = 'Failed to save skills. Please check your connection.'
  } finally {
    skillsSaving.value = false
  }
}

async function submitSkillForm() {
  const { name, description, instructions } = skillForm.value
  if (!name.trim() || !description.trim() || !instructions.trim()) {
    skillNameError.value = 'All fields are required.'
    return
  }
  // Check name uniqueness (excluding current edit target)
  const duplicate = skills.value.find(s => s.name === name.trim() && s.id !== editingSkillId.value)
  if (duplicate) {
    skillNameError.value = `A skill named "${name.trim()}" already exists.`
    return
  }

  let updated: Skill[]
  if (editingSkillId.value) {
    updated = skills.value.map(s => s.id === editingSkillId.value
      ? { ...s, name: name.trim(), description: description.trim(), instructions: instructions.trim() }
      : s
    )
  } else {
    const newSkill: Skill = {
      id: crypto.randomUUID(),
      name: name.trim(),
      description: description.trim(),
      instructions: instructions.trim(),
    }
    updated = [...skills.value, newSkill]
  }

  await saveSkills(updated)
  if (!skillsError.value) {
    showSkillForm.value = false
    editingSkillId.value = null
  }
}

async function deleteSkill(id: string) {
  const updated = skills.value.filter(s => s.id !== id)
  await saveSkills(updated)
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

      <!-- Task Archiving -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">Task Archiving</h3>
        <div class="flex items-center gap-3">
          <label for="archive-after-days" class="text-sm font-medium text-gray-700">Archive after (days)</label>
          <input
            id="archive-after-days"
            v-model.number="archiveAfterDays"
            type="number"
            min="1"
            class="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          <button
            @click="saveArchiveAfterDays"
            :disabled="archiveSaving"
            class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {{ archiveSaving ? 'Saving...' : 'Save' }}
          </button>
          <span v-if="archiveSuccess" class="text-sm text-green-600">Archive setting saved.</span>
        </div>
      </div>

      <!-- Task Runner -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">Task Runner</h3>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Log Level</label>
          <div class="flex items-center gap-3">
            <select
              v-model="taskRunnerLogLevel"
              :disabled="taskRunnerLogLevelSaving"
              class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              @change="onTaskRunnerLogLevelChange"
              data-testid="task-runner-log-level-select"
            >
              <option value="INFO">INFO</option>
              <option value="DEBUG">DEBUG</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
            <span v-if="taskRunnerLogLevelSaving" class="text-sm text-gray-500">Saving...</span>
            <span v-if="taskRunnerLogLevelSuccess" class="text-sm text-green-600">Log level saved.</span>
          </div>
        </div>
      </div>

      <!-- MCP API Key -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">MCP API Key</h3>

        <div v-if="mcpApiKey" class="space-y-4">
          <!-- Key display -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
            <div class="flex items-center gap-2">
              <code class="flex-1 rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-sm font-mono break-all">{{ mcpApiKeyRevealed ? mcpApiKey : '\u2022'.repeat(32) }}</code>
              <button
                @click="mcpApiKeyRevealed = !mcpApiKeyRevealed"
                class="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                data-testid="mcp-key-reveal"
              >
                {{ mcpApiKeyRevealed ? 'Hide' : 'Reveal' }}
              </button>
              <button
                @click="copyMcpApiKey"
                class="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                data-testid="mcp-key-copy"
              >
                {{ mcpApiKeyCopied ? 'Copied!' : 'Copy' }}
              </button>
            </div>
          </div>

          <!-- Regenerate -->
          <div class="flex items-center gap-3">
            <button
              @click="showRegenerateConfirm"
              :disabled="mcpKeyRegenerating"
              class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              data-testid="mcp-key-regenerate"
            >
              {{ mcpKeyRegenerating ? 'Regenerating...' : 'Regenerate' }}
            </button>
            <span v-if="mcpKeyRegenerateSuccess" class="text-sm text-green-600">API key regenerated.</span>
            <span v-if="mcpKeyRegenerateError" class="text-sm text-red-600">{{ mcpKeyRegenerateError }}</span>
          </div>

          <!-- Example config -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Example MCP Configuration</label>
            <pre class="rounded-md border border-gray-300 bg-gray-50 p-3 text-xs font-mono overflow-x-auto">{{ mcpMaskedConfig() }}</pre>
            <button
              @click="copyMcpConfig"
              class="mt-2 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              data-testid="mcp-config-copy"
            >
              {{ mcpConfigCopied ? 'Copied!' : 'Copy Configuration' }}
            </button>
          </div>
        </div>

        <div v-else class="text-sm text-gray-500">
          No API key generated. Restart the backend to auto-generate one.
        </div>
      </div>

      <!-- Git SSH Key -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <h3 class="text-lg font-semibold text-gray-800 mb-3">Git SSH Key</h3>

        <div v-if="sshPublicKey" class="space-y-4">
          <!-- Public key display -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Public Key</label>
            <div class="flex items-start gap-2">
              <code class="flex-1 rounded-md border border-gray-300 bg-gray-50 px-3 py-2 text-xs font-mono break-all" data-testid="ssh-public-key">{{ sshPublicKey }}</code>
              <button
                @click="copySshPublicKey"
                class="shrink-0 rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                data-testid="ssh-key-copy"
              >
                {{ sshKeyCopied ? 'Copied!' : 'Copy' }}
              </button>
            </div>
            <p class="mt-1 text-xs text-gray-500">Add this key as a deploy key to your Git repositories. Enable write access if you want the agent to push changes.</p>
          </div>

          <!-- Regenerate -->
          <div class="flex items-center gap-3">
            <button
              @click="showSshRegenerateConfirm"
              :disabled="sshKeyRegenerating"
              class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              data-testid="ssh-key-regenerate"
            >
              {{ sshKeyRegenerating ? 'Regenerating...' : 'Regenerate' }}
            </button>
            <span v-if="sshKeyRegenerateSuccess" class="text-sm text-green-600">SSH key regenerated.</span>
            <span v-if="sshKeyRegenerateError" class="text-sm text-red-600">{{ sshKeyRegenerateError }}</span>
          </div>

          <!-- SSH hosts list -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">SSH Hosts</label>
            <p class="text-xs text-gray-500 mb-2">Git hosts that should use SSH authentication.</p>
            <div v-if="sshHostsError" class="mb-2 text-sm text-red-600">{{ sshHostsError }}</div>
            <div class="space-y-1 mb-2">
              <div
                v-for="(host, index) in gitSshHosts"
                :key="host"
                class="flex items-center gap-2"
              >
                <code class="text-sm font-mono text-gray-800">{{ host }}</code>
                <button
                  @click="removeSshHost(index)"
                  class="text-xs text-red-600 hover:text-red-800"
                  data-testid="ssh-host-remove"
                >Remove</button>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <input
                v-model="newSshHost"
                type="text"
                class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                placeholder="e.g. gitlab.com"
                @keyup.enter="addSshHost"
                data-testid="ssh-host-input"
              />
              <button
                @click="addSshHost"
                class="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                data-testid="ssh-host-add"
              >Add Host</button>
            </div>
            <div class="mt-3 flex items-center gap-3">
              <button
                @click="saveSshHosts"
                :disabled="sshHostsSaving"
                class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                data-testid="ssh-hosts-save"
              >
                {{ sshHostsSaving ? 'Saving...' : 'Save' }}
              </button>
              <span v-if="sshHostsSuccess" class="text-sm text-green-600">SSH hosts saved.</span>
            </div>
          </div>
        </div>

        <div v-else class="text-sm text-gray-500" data-testid="ssh-no-key">
          No SSH key generated. Restart the backend to auto-generate one.
        </div>
      </div>

      <!-- Skills -->
      <div class="mb-6 rounded-lg bg-white p-6 shadow">
        <button
          @click="skillsExpanded = !skillsExpanded"
          class="flex w-full items-center justify-between text-left"
        >
          <h3 class="text-lg font-semibold text-gray-800">
            Skills
            <span class="ml-2 text-sm font-normal text-gray-500">({{ skills.length }})</span>
          </h3>
          <svg
            :class="{ 'rotate-180': skillsExpanded }"
            class="h-5 w-5 text-gray-500 transition-transform"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        <div v-if="skillsExpanded" class="mt-3">
          <p class="text-sm text-gray-500 mb-3">Reusable prompt templates the task runner agent can load on demand via MCP tools.</p>
          <div v-if="skillsError" class="mb-2 text-sm text-red-600">{{ skillsError }}</div>
          <div v-if="skillsSuccess" class="mb-2 text-sm text-green-600">Skills saved.</div>

          <!-- Skill list -->
          <div v-if="skills.length > 0 && !showSkillForm" class="space-y-2 mb-3">
            <div
              v-for="skill in skills"
              :key="skill.id"
              class="flex items-start justify-between rounded-md border border-gray-200 p-3"
            >
              <div>
                <div class="text-sm font-medium text-gray-800">{{ skill.name }}</div>
                <div class="text-xs text-gray-500">{{ skill.description }}</div>
              </div>
              <div class="flex gap-2 ml-3 shrink-0">
                <button
                  @click="openEditSkill(skill)"
                  class="text-xs text-blue-600 hover:text-blue-800"
                  data-testid="skill-edit"
                >Edit</button>
                <button
                  @click="deleteSkill(skill.id)"
                  :disabled="skillsSaving"
                  class="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
                  data-testid="skill-delete"
                >Delete</button>
              </div>
            </div>
          </div>

          <div v-if="skills.length === 0 && !showSkillForm" class="text-sm text-gray-400 mb-3">No skills defined yet.</div>

          <!-- Add/Edit form -->
          <div v-if="showSkillForm" class="rounded-md border border-gray-200 p-4 mb-3 space-y-3">
            <h4 class="text-sm font-semibold text-gray-700">{{ editingSkillId ? 'Edit Skill' : 'New Skill' }}</h4>
            <div v-if="skillNameError" class="text-sm text-red-600">{{ skillNameError }}</div>
            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Name</label>
              <input
                v-model="skillForm.name"
                type="text"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                placeholder="e.g. researcher"
                data-testid="skill-name-input"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Description</label>
              <input
                v-model="skillForm.description"
                type="text"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                placeholder="Brief summary for agent discovery"
                data-testid="skill-description-input"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Instructions</label>
              <textarea
                v-model="skillForm.instructions"
                rows="6"
                class="w-full rounded-md border border-gray-300 p-3 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                placeholder="Full prompt instructions the agent will follow..."
                data-testid="skill-instructions-input"
              ></textarea>
            </div>
            <div class="flex gap-2">
              <button
                @click="submitSkillForm"
                :disabled="skillsSaving"
                class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                data-testid="skill-save"
              >
                {{ skillsSaving ? 'Saving...' : (editingSkillId ? 'Update' : 'Add') }}
              </button>
              <button
                @click="cancelSkillForm"
                class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                data-testid="skill-cancel"
              >Cancel</button>
            </div>
          </div>

          <button
            v-if="!showSkillForm"
            @click="openAddSkill"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            data-testid="skill-add"
          >Add Skill</button>
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

    <!-- Regenerate API key confirmation dialog -->
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
          <button
            type="button"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            @click="cancelRegenerate"
            data-testid="mcp-regenerate-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
            @click="confirmRegenerate"
            data-testid="mcp-regenerate-confirm"
          >
            Regenerate
          </button>
        </div>
      </div>
    </dialog>
    <!-- Regenerate SSH key confirmation dialog -->
    <dialog
      ref="sshRegenerateDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelSshRegenerate"
      @click="onSshRegenerateDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Regenerate SSH key?</h3>
        <p class="mb-4 text-sm text-gray-600">This will invalidate the current key. Deploy keys configured with the old public key will stop working.</p>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            @click="cancelSshRegenerate"
            data-testid="ssh-regenerate-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
            @click="confirmSshRegenerate"
            data-testid="ssh-regenerate-confirm"
          >
            Regenerate
          </button>
        </div>
      </div>
    </dialog>
  </div>
</template>
