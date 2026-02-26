<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchTaskProfiles,
  createTaskProfile,
  updateTaskProfile,
  deleteTaskProfile,
  fetchLitellmMcpServers,
  fetchLlmModels,
  type TaskProfile,
} from '../../composables/useApi'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()

const profiles = ref<TaskProfile[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const showForm = ref(false)
const editingId = ref<string | null>(null)

// Available options for dropdowns and three-state selectors
const availableModels = ref<string[]>([])
const defaultModel = ref('')
const defaultMaxTurns = ref<string>('')
const defaultReasoningEffort = ref('')
const availableMcpServers = ref<string[]>([])
const availableLitellmServers = ref<string[]>([])
const availableSkills = ref<{ id: string; name: string }[]>([])

// Form fields
const formName = ref('')
const formDescription = ref('')
const formMatchRules = ref('')
const formModel = ref('')
const formSystemPrompt = ref('')
const formMaxTurns = ref<string>('')
const formReasoningEffort = ref('')

// Three-state: 'inherit' | 'none' | 'select'
const formMcpMode = ref<'inherit' | 'none' | 'select'>('inherit')
const formMcpSelected = ref<string[]>([])
const formLitellmMode = ref<'inherit' | 'none' | 'select'>('inherit')
const formLitellmSelected = ref<string[]>([])
const formSkillMode = ref<'inherit' | 'none' | 'select'>('inherit')
const formSkillSelected = ref<string[]>([])

// Delete dialog
const showDeleteDialog = ref(false)
const deleteDialogRef = ref<HTMLDialogElement | null>(null)
const pendingDeleteId = ref<string | null>(null)

const reasoningEffortOptions = ['', 'low', 'medium', 'high']

const overrideSummary = computed(() => {
  return (profile: TaskProfile) => {
    const overrides: string[] = []
    if (profile.model) overrides.push('Model')
    if (profile.system_prompt) overrides.push('Prompt')
    if (profile.max_turns != null) overrides.push('Max turns')
    if (profile.reasoning_effort) overrides.push('Reasoning')
    if (profile.mcp_servers != null) overrides.push('MCP')
    if (profile.litellm_mcp_servers != null) overrides.push('LiteLLM')
    if (profile.skill_ids != null) overrides.push('Skills')
    return overrides.length ? overrides.join(', ') : 'No overrides'
  }
})

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) headers['Authorization'] = `Bearer ${auth.token}`
  return fetch(url, { ...options, headers })
}

async function loadProfiles() {
  loading.value = true
  error.value = null
  try {
    profiles.value = await fetchTaskProfiles()
  } catch {
    error.value = 'Failed to load profiles.'
  } finally {
    loading.value = false
  }
}

function extractSettingValue(data: any, key: string, fallback: string = ''): string {
  const entry = data[key]
  if (entry && typeof entry === 'object' && 'value' in entry) return entry.value ?? fallback
  return entry ?? fallback
}

async function loadOptions() {
  try {
    // Load settings for defaults and MCP server names
    const settingsRes = await authFetch('/api/settings')
    if (settingsRes.ok) {
      const data = await settingsRes.json()
      defaultModel.value = extractSettingValue(data, 'task_processing_model', '')
      const mcpRaw = data.mcp_servers?.value ?? data.mcp_servers
      if (mcpRaw && typeof mcpRaw === 'object') {
        const servers = mcpRaw.mcpServers
        if (servers && typeof servers === 'object') {
          availableMcpServers.value = Object.keys(servers)
        }
      }
    }
  } catch { /* ignore */ }

  try {
    availableModels.value = await fetchLlmModels()
  } catch { /* ignore */ }

  try {
    // Load runtime defaults from worker config endpoint
    const runtimeRes = await authFetch('/api/worker/defaults')
    if (runtimeRes.ok) {
      const data = await runtimeRes.json()
      defaultMaxTurns.value = data.max_turns ?? ''
      defaultReasoningEffort.value = data.reasoning_effort ?? ''
    }
  } catch { /* ignore */ }

  try {
    const litellmData = await fetchLitellmMcpServers()
    if (litellmData.available) {
      availableLitellmServers.value = Object.keys(litellmData.servers)
    }
  } catch { /* ignore */ }

  try {
    const skillsRes = await authFetch('/api/skills')
    if (skillsRes.ok) {
      const data = await skillsRes.json()
      availableSkills.value = data.map((s: any) => ({ id: s.id, name: s.name }))
    }
  } catch { /* ignore */ }
}

function resetForm() {
  formName.value = ''
  formDescription.value = ''
  formMatchRules.value = ''
  formModel.value = ''
  formSystemPrompt.value = ''
  formMaxTurns.value = ''
  formReasoningEffort.value = ''
  formMcpMode.value = 'inherit'
  formMcpSelected.value = []
  formLitellmMode.value = 'inherit'
  formLitellmSelected.value = []
  formSkillMode.value = 'inherit'
  formSkillSelected.value = []
}

function openAdd() {
  editingId.value = null
  resetForm()
  showForm.value = true
}

function openEdit(profile: TaskProfile) {
  editingId.value = profile.id
  formName.value = profile.name
  formDescription.value = profile.description || ''
  formMatchRules.value = profile.match_rules || ''
  formModel.value = profile.model || ''
  formSystemPrompt.value = profile.system_prompt || ''
  formMaxTurns.value = profile.max_turns != null ? String(profile.max_turns) : ''
  formReasoningEffort.value = profile.reasoning_effort || ''

  if (profile.mcp_servers === null) {
    formMcpMode.value = 'inherit'
    formMcpSelected.value = []
  } else if (profile.mcp_servers.length === 0) {
    formMcpMode.value = 'none'
    formMcpSelected.value = []
  } else {
    formMcpMode.value = 'select'
    formMcpSelected.value = [...profile.mcp_servers]
  }

  if (profile.litellm_mcp_servers === null) {
    formLitellmMode.value = 'inherit'
    formLitellmSelected.value = []
  } else if (profile.litellm_mcp_servers.length === 0) {
    formLitellmMode.value = 'none'
    formLitellmSelected.value = []
  } else {
    formLitellmMode.value = 'select'
    formLitellmSelected.value = [...profile.litellm_mcp_servers]
  }

  if (profile.skill_ids === null) {
    formSkillMode.value = 'inherit'
    formSkillSelected.value = []
  } else if (profile.skill_ids.length === 0) {
    formSkillMode.value = 'none'
    formSkillSelected.value = []
  } else {
    formSkillMode.value = 'select'
    formSkillSelected.value = [...profile.skill_ids]
  }

  showForm.value = true
}

function cancelForm() {
  showForm.value = false
  editingId.value = null
  error.value = null
}

function buildPayload(): Record<string, unknown> {
  const payload: Record<string, unknown> = { name: formName.value.trim() }
  if (formDescription.value.trim()) payload.description = formDescription.value.trim()
  else payload.description = null
  if (formMatchRules.value.trim()) payload.match_rules = formMatchRules.value.trim()
  else payload.match_rules = null
  if (formModel.value.trim()) payload.model = formModel.value.trim()
  else payload.model = null
  if (formSystemPrompt.value.trim()) payload.system_prompt = formSystemPrompt.value.trim()
  else payload.system_prompt = null
  if (formMaxTurns.value.trim()) payload.max_turns = parseInt(formMaxTurns.value.trim(), 10)
  else payload.max_turns = null
  if (formReasoningEffort.value) payload.reasoning_effort = formReasoningEffort.value
  else payload.reasoning_effort = null

  if (formMcpMode.value === 'inherit') payload.mcp_servers = null
  else if (formMcpMode.value === 'none') payload.mcp_servers = []
  else payload.mcp_servers = formMcpSelected.value

  if (formLitellmMode.value === 'inherit') payload.litellm_mcp_servers = null
  else if (formLitellmMode.value === 'none') payload.litellm_mcp_servers = []
  else payload.litellm_mcp_servers = formLitellmSelected.value

  if (formSkillMode.value === 'inherit') payload.skill_ids = null
  else if (formSkillMode.value === 'none') payload.skill_ids = []
  else payload.skill_ids = formSkillSelected.value

  return payload
}

async function submitForm() {
  if (!formName.value.trim()) {
    error.value = 'Name is required.'
    return
  }
  saving.value = true
  error.value = null
  try {
    const payload = buildPayload()
    if (editingId.value) {
      await updateTaskProfile(editingId.value, payload)
      toast.success('Profile updated.')
    } else {
      await createTaskProfile(payload)
      toast.success('Profile created.')
    }
    showForm.value = false
    editingId.value = null
    await loadProfiles()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save profile.'
  } finally {
    saving.value = false
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

  saving.value = true
  error.value = null
  try {
    await deleteTaskProfile(id)
    await loadProfiles()
    toast.success('Profile deleted.')
  } catch {
    error.value = 'Failed to delete profile.'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadProfiles()
  loadOptions()
})
</script>

<template>
  <div data-testid="task-profiles-page">
    <div v-if="error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700" data-testid="profiles-error">
      {{ error }}
    </div>

    <div v-if="loading" class="space-y-3">
      <div v-for="n in 3" :key="n" class="rounded-lg bg-white p-4 shadow">
        <div class="h-5 w-40 rounded bg-gray-200 animate-pulse mb-2"></div>
        <div class="h-4 w-64 rounded bg-gray-200 animate-pulse"></div>
      </div>
    </div>

    <template v-else>
      <!-- Profile list -->
      <div v-if="profiles.length > 0 && !showForm" class="space-y-3 mb-4">
        <div
          v-for="profile in profiles"
          :key="profile.id"
          class="rounded-lg bg-white p-4 shadow"
          data-testid="profile-card"
        >
          <div class="flex items-start justify-between">
            <div class="flex-1">
              <div class="text-sm font-semibold text-gray-800">{{ profile.name }}</div>
              <div v-if="profile.description" class="mt-0.5 text-xs text-gray-500">{{ profile.description }}</div>
              <div class="mt-1 text-xs text-gray-400">
                <span v-if="profile.model" class="mr-3">Model: {{ profile.model }}</span>
                <span>{{ overrideSummary(profile) }}</span>
              </div>
            </div>
            <div class="flex gap-2 ml-3 shrink-0">
              <button
                @click="openEdit(profile)"
                class="text-xs text-blue-600 hover:text-blue-800"
                data-testid="profile-edit"
              >
                Edit
              </button>
              <button
                @click="requestDelete(profile.id)"
                :disabled="saving"
                class="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
                data-testid="profile-delete"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-if="profiles.length === 0 && !showForm && !loading"
        class="rounded-lg bg-white p-6 shadow text-center"
        data-testid="profiles-empty-state"
      >
        <p class="text-sm text-gray-500 mb-3">No task profiles defined. Profiles let you configure different models, tools, and instructions for different types of tasks.</p>
        <button
          @click="openAdd"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          data-testid="profile-add-empty"
        >
          Add Profile
        </button>
      </div>

      <!-- Add/Edit form -->
      <div v-if="showForm" class="rounded-lg bg-white p-6 shadow" data-testid="profile-form">
        <h3 class="text-lg font-semibold text-gray-800 mb-4">{{ editingId ? 'Edit Profile' : 'New Profile' }}</h3>

        <div class="space-y-4">
          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Name</label>
            <input
              v-model="formName"
              type="text"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              placeholder="e.g. email-triage"
              data-testid="profile-name-input"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Description</label>
            <input
              v-model="formDescription"
              type="text"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              placeholder="Brief summary of this profile's purpose"
              data-testid="profile-description-input"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">Match Rules</label>
            <textarea
              v-model="formMatchRules"
              rows="2"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              placeholder="Natural language description of what tasks this profile matches..."
              data-testid="profile-match-rules-input"
            ></textarea>
            <p class="mt-1 text-xs text-gray-400">Used by the LLM classifier to auto-assign this profile to matching tasks.</p>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Model</label>
              <select
                v-model="formModel"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                data-testid="profile-model-input"
              >
                <option value="">Use default{{ defaultModel ? ` (${defaultModel})` : '' }}</option>
                <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
                <option v-if="formModel && !availableModels.includes(formModel)" :value="formModel">{{ formModel }}</option>
              </select>
            </div>

            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Reasoning Effort</label>
              <select
                v-model="formReasoningEffort"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                data-testid="profile-reasoning-effort-select"
              >
                <option value="">Use default{{ defaultReasoningEffort ? ` (${defaultReasoningEffort})` : ' (medium)' }}</option>
                <option v-for="opt in reasoningEffortOptions.filter(o => o)" :key="opt" :value="opt">{{ opt }}</option>
              </select>
            </div>

            <div>
              <label class="block text-xs font-medium text-gray-600 mb-1">Max Turns</label>
              <input
                v-model="formMaxTurns"
                type="number"
                min="1"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                :placeholder="defaultMaxTurns ? `Use default (${defaultMaxTurns})` : 'Use default (not set)'"
                data-testid="profile-max-turns-input"
              />
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">System Prompt</label>
            <textarea
              v-model="formSystemPrompt"
              rows="3"
              class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              placeholder="Leave blank to inherit default system prompt"
              data-testid="profile-system-prompt-input"
            ></textarea>
          </div>

          <!-- Three-state: MCP Servers -->
          <div v-if="availableMcpServers.length > 0">
            <label class="block text-xs font-medium text-gray-600 mb-2">MCP Servers</label>
            <div class="flex gap-4 mb-2">
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formMcpMode" value="inherit" class="text-blue-600" />
                Inherit default
              </label>
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formMcpMode" value="none" class="text-blue-600" />
                None
              </label>
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formMcpMode" value="select" class="text-blue-600" />
                Select specific
              </label>
            </div>
            <div v-if="formMcpMode === 'select'" class="ml-4 space-y-1" data-testid="profile-mcp-checkboxes">
              <label v-for="server in availableMcpServers" :key="server" class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="checkbox" :value="server" v-model="formMcpSelected" class="text-blue-600" />
                {{ server }}
              </label>
            </div>
          </div>

          <!-- Three-state: LiteLLM MCP Servers -->
          <div v-if="availableLitellmServers.length > 0">
            <label class="block text-xs font-medium text-gray-600 mb-2">LiteLLM MCP Servers</label>
            <div class="flex gap-4 mb-2">
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formLitellmMode" value="inherit" class="text-blue-600" />
                Inherit default
              </label>
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formLitellmMode" value="none" class="text-blue-600" />
                None
              </label>
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formLitellmMode" value="select" class="text-blue-600" />
                Select specific
              </label>
            </div>
            <div v-if="formLitellmMode === 'select'" class="ml-4 space-y-1" data-testid="profile-litellm-checkboxes">
              <label v-for="server in availableLitellmServers" :key="server" class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="checkbox" :value="server" v-model="formLitellmSelected" class="text-blue-600" />
                {{ server }}
              </label>
            </div>
          </div>

          <!-- Three-state: Skills -->
          <div v-if="availableSkills.length > 0">
            <label class="block text-xs font-medium text-gray-600 mb-2">Skills</label>
            <div class="flex gap-4 mb-2">
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formSkillMode" value="inherit" class="text-blue-600" />
                Inherit all
              </label>
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formSkillMode" value="none" class="text-blue-600" />
                None
              </label>
              <label class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="radio" v-model="formSkillMode" value="select" class="text-blue-600" />
                Select specific
              </label>
            </div>
            <div v-if="formSkillMode === 'select'" class="ml-4 space-y-1" data-testid="profile-skills-checkboxes">
              <label v-for="skill in availableSkills" :key="skill.id" class="flex items-center gap-1.5 text-xs text-gray-600">
                <input type="checkbox" :value="skill.id" v-model="formSkillSelected" class="text-blue-600" />
                {{ skill.name }}
              </label>
            </div>
          </div>

          <div class="flex gap-2 pt-2">
            <button
              @click="submitForm"
              :disabled="saving"
              class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              data-testid="profile-save"
            >
              {{ saving ? 'Saving...' : (editingId ? 'Update' : 'Create') }}
            </button>
            <button
              @click="cancelForm"
              class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              data-testid="profile-cancel"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>

      <!-- Add button (when list is showing) -->
      <button
        v-if="profiles.length > 0 && !showForm"
        @click="openAdd"
        class="mt-4 rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        data-testid="profile-add"
      >
        Add Profile
      </button>
    </template>

    <!-- Delete confirmation dialog -->
    <dialog
      ref="deleteDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelDelete"
      @click="onDeleteDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Delete profile?</h3>
        <p class="mb-4 text-sm text-gray-600">Any tasks using this profile will revert to default settings. This action cannot be undone.</p>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            @click="cancelDelete"
            data-testid="profile-delete-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
            @click="confirmDelete"
            data-testid="profile-delete-confirm"
          >
            Delete
          </button>
        </div>
      </div>
    </dialog>
  </div>
</template>
