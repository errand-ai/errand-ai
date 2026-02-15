<script setup lang="ts">
import { onMounted, ref, computed, onBeforeUnmount } from 'vue'
import { useAuthStore } from '../stores/auth'
import SystemPromptSettings from '../components/settings/SystemPromptSettings.vue'
import SkillsSettings from '../components/settings/SkillsSettings.vue'
import LlmModelSettings from '../components/settings/LlmModelSettings.vue'
import TaskManagementSettings from '../components/settings/TaskManagementSettings.vue'
import McpApiKeySettings from '../components/settings/McpApiKeySettings.vue'
import GitSshKeySettings from '../components/settings/GitSshKeySettings.vue'
import McpServerConfigSettings from '../components/settings/McpServerConfigSettings.vue'

const auth = useAuthStore()

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'
const DEFAULT_TASK_PROCESSING_MODEL = 'claude-sonnet-4-5-20250929'

// Loaded settings state
const systemPrompt = ref('')
const mcpServersText = ref('')
const llmModel = ref(DEFAULT_MODEL)
const taskProcessingModel = ref(DEFAULT_TASK_PROCESSING_MODEL)
const transcriptionModel = ref<string>('')
const taskRunnerLogLevel = ref('INFO')
const timezoneValue = ref('UTC')
const archiveAfterDays = ref(3)
const mcpApiKey = ref<string | null>(null)
const sshPublicKey = ref<string | null>(null)
const gitSshHosts = ref<string[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// Child component refs for dirty detection
const systemPromptRef = ref<InstanceType<typeof SystemPromptSettings> | null>(null)
const llmModelRef = ref<InstanceType<typeof LlmModelSettings> | null>(null)
const taskMgmtRef = ref<InstanceType<typeof TaskManagementSettings> | null>(null)
const mcpConfigRef = ref<InstanceType<typeof McpServerConfigSettings> | null>(null)

const hasUnsavedChanges = computed(() =>
  systemPromptRef.value?.isDirty
  || llmModelRef.value?.isDirty
  || taskMgmtRef.value?.isDirty
  || mcpConfigRef.value?.isDirty
)

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (hasUnsavedChanges.value) {
    e.preventDefault()
  }
}

async function settingsFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

async function saveSettings(data: Record<string, unknown>): Promise<void> {
  const res = await settingsFetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (res.status === 403) throw new Error('Access denied — admin role required.')
  if (!res.ok) throw new Error(`Failed to save settings (HTTP ${res.status})`)
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
  } catch {
    error.value = 'Failed to load settings. Please check your connection.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  window.addEventListener('beforeunload', onBeforeUnload)
  await loadSettings()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
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
      <!-- ===== Agent Configuration ===== -->
      <h3 class="text-lg font-semibold text-gray-600 uppercase tracking-wide mb-4" data-testid="group-agent-configuration">Agent Configuration</h3>

      <SystemPromptSettings
        ref="systemPromptRef"
        :system-prompt="systemPrompt"
        :save-settings="saveSettings"
        @update:system-prompt="systemPrompt = $event"
      />

      <SkillsSettings />

      <LlmModelSettings
        ref="llmModelRef"
        :llm-model="llmModel"
        :task-processing-model="taskProcessingModel"
        :transcription-model="transcriptionModel"
        @update:llm-model="llmModel = $event"
        @update:task-processing-model="taskProcessingModel = $event"
        @update:transcription-model="transcriptionModel = $event"
      />

      <!-- ===== Task Management ===== -->
      <h3 class="text-lg font-semibold text-gray-600 uppercase tracking-wide mb-4 mt-8" data-testid="group-task-management">Task Management</h3>

      <TaskManagementSettings
        ref="taskMgmtRef"
        :timezone="timezoneValue"
        :archive-after-days="archiveAfterDays"
        :task-runner-log-level="taskRunnerLogLevel"
        :save-settings="saveSettings"
        @update:timezone="timezoneValue = $event"
        @update:archive-after-days="archiveAfterDays = $event"
        @update:task-runner-log-level="taskRunnerLogLevel = $event"
      />

      <!-- ===== Integrations & Security ===== -->
      <h3 class="text-lg font-semibold text-gray-600 uppercase tracking-wide mb-4 mt-8" data-testid="group-integrations-security">Integrations & Security</h3>

      <McpApiKeySettings
        :mcp-api-key="mcpApiKey"
        @update:mcp-api-key="mcpApiKey = $event"
      />

      <GitSshKeySettings
        :ssh-public-key="sshPublicKey"
        :git-ssh-hosts="gitSshHosts"
        :save-settings="saveSettings"
        @update:ssh-public-key="sshPublicKey = $event"
        @update:git-ssh-hosts="gitSshHosts = $event"
      />

      <McpServerConfigSettings
        ref="mcpConfigRef"
        :mcp-servers-text="mcpServersText"
        :save-settings="saveSettings"
        @update:mcp-servers-text="mcpServersText = $event"
      />
    </template>
  </div>
</template>
