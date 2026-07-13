<script setup lang="ts">
import { onMounted, ref, provide } from 'vue'
import { useRouter } from 'vue-router'
import { SettingsShell } from '@errand-ai/ui-components'
import type { SettingsSection } from '@errand-ai/ui-components'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

// Section ids map 1:1 to the child route path segment / route name (`settings-<id>`).
// <SettingsShell> derives the active section from the current route and emits
// `section-change` on navigation; we translate that into a router push.
const sections: SettingsSection[] = [
  { id: 'agent', label: 'Agent Configuration' },
  { id: 'tasks', label: 'Task Management' },
  { id: 'security', label: 'Security' },
  { id: 'profiles', label: 'Task Profiles' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'task-generators', label: 'Task Generators' },
  { id: 'cloud', label: 'Cloud Service' },
  { id: 'users', label: 'User Management' },
]

function onSectionChange(id: string) {
  router.push({ name: `settings-${id}` })
}

const DEFAULT_MODEL = 'claude-haiku-4-5-20251001'
const DEFAULT_TASK_PROCESSING_MODEL = 'claude-sonnet-4-5-20250929'

// Settings state (provided to child routes)
const systemPrompt = ref('')
const mcpServersText = ref('')
const llmModel = ref(DEFAULT_MODEL)
const taskProcessingModel = ref(DEFAULT_TASK_PROCESSING_MODEL)
const transcriptionModel = ref<string>('')
const taskRunnerLogLevel = ref('INFO')
const timezoneValue = ref('UTC')
const titleGenerationTimeout = ref(30)
const taskProcessingTimeout = ref(30)
const transcriptionTimeout = ref(30)
const archiveAfterDays = ref(3)
const maxConcurrentTasks = ref(3)
const pluginPollIntervalSeconds = ref(21600)
const mcpApiKey = ref<string | null>(null)
const sshPublicKey = ref<string | null>(null)
const gitSshHosts = ref<string[]>([])
const skillsGitRepo = ref<{ url?: string; branch?: string; path?: string } | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const settingsMetadata = ref<Record<string, { value: any; source: string; sensitive: boolean; readonly: boolean }>>({})

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

function extractValue(data: Record<string, any>, key: string, fallback: any = ''): any {
  const entry = data[key]
  if (entry && typeof entry === 'object' && 'value' in entry) {
    return entry.value ?? fallback
  }
  // Backwards compat: plain value format
  return entry ?? fallback
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

    // Store metadata if present
    const isMetadataFormat = data.system_prompt && typeof data.system_prompt === 'object' && 'value' in data.system_prompt
    if (isMetadataFormat) {
      settingsMetadata.value = data
    }

    systemPrompt.value = extractValue(data, 'system_prompt', '')
    const mcpRaw = extractValue(data, 'mcp_servers', null)
    mcpServersText.value = mcpRaw ? JSON.stringify(mcpRaw, null, 2) : ''
    mcpApiKey.value = extractValue(data, 'mcp_api_key', null)
    sshPublicKey.value = extractValue(data, 'ssh_public_key', null)
    const hosts = extractValue(data, 'git_ssh_hosts', null)
    gitSshHosts.value = Array.isArray(hosts) ? hosts : ['github.com', 'bitbucket.org']
    llmModel.value = extractValue(data, 'llm_model', DEFAULT_MODEL)
    taskProcessingModel.value = extractValue(data, 'task_processing_model', DEFAULT_TASK_PROCESSING_MODEL)
    transcriptionModel.value = extractValue(data, 'transcription_model', '')
    titleGenerationTimeout.value = extractValue(data, 'title_generation_timeout', 30)
    taskProcessingTimeout.value = extractValue(data, 'task_processing_timeout', 30)
    transcriptionTimeout.value = extractValue(data, 'transcription_timeout', 30)
    taskRunnerLogLevel.value = extractValue(data, 'task_runner_log_level', 'INFO') || 'INFO'
    timezoneValue.value = extractValue(data, 'timezone', 'UTC')
    archiveAfterDays.value = extractValue(data, 'archive_after_days', 3)
    maxConcurrentTasks.value = extractValue(data, 'max_concurrent_tasks', 3)
    pluginPollIntervalSeconds.value = extractValue(data, 'plugin_poll_interval_seconds', 21600)
    skillsGitRepo.value = extractValue(data, 'skills_git_repo', null)
  } catch {
    error.value = 'Failed to load settings. Please check your connection.'
  } finally {
    loading.value = false
  }
}

provide('settings-state', {
  systemPrompt,
  mcpServersText,
  llmModel,
  taskProcessingModel,
  transcriptionModel,
  titleGenerationTimeout,
  taskProcessingTimeout,
  transcriptionTimeout,
  taskRunnerLogLevel,
  timezoneValue,
  archiveAfterDays,
  maxConcurrentTasks,
  pluginPollIntervalSeconds,
  mcpApiKey,
  sshPublicKey,
  gitSshHosts,
  skillsGitRepo,
  settingsMetadata,
  saveSettings,
})

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <SettingsShell
      :sections="sections"
      :loading="loading"
      :error="error"
      @section-change="onSectionChange"
    >
      <!-- Wave 2 cards still consume the `settings-state` provided after loadSettings.
           Those cards snapshot their props on mount, so the sub-page must not mount
           until settings have loaded, matching the pre-shell `v-else` ordering. -->
      <router-view v-if="!loading" />
    </SettingsShell>
  </div>
</template>
