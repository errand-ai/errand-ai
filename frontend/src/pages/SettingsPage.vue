<script setup lang="ts">
import { onMounted, ref, provide } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()

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
const llmTimeout = ref(30)
const archiveAfterDays = ref(3)
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
    llmTimeout.value = extractValue(data, 'llm_timeout', 30)
    taskRunnerLogLevel.value = extractValue(data, 'task_runner_log_level', 'INFO') || 'INFO'
    timezoneValue.value = extractValue(data, 'timezone', 'UTC')
    archiveAfterDays.value = extractValue(data, 'archive_after_days', 3)
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
  llmTimeout,
  taskRunnerLogLevel,
  timezoneValue,
  archiveAfterDays,
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
    <h2 class="text-2xl font-bold text-gray-900 mb-6">Settings</h2>

    <div v-if="error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
      {{ error }}
    </div>

    <div v-if="loading" class="space-y-6" data-testid="settings-skeleton">
      <div v-for="n in 4" :key="n" class="rounded-lg bg-white p-6 shadow">
        <div class="h-5 w-48 rounded bg-gray-200 animate-pulse mb-4"></div>
        <div class="space-y-3">
          <div class="h-4 w-full rounded bg-gray-200 animate-pulse"></div>
          <div class="h-4 w-3/4 rounded bg-gray-200 animate-pulse"></div>
        </div>
      </div>
    </div>

    <div v-else class="flex gap-8">
      <nav class="w-48 flex-shrink-0" data-testid="settings-sidebar">
        <div class="sticky top-6 space-y-1">
          <router-link
            to="/settings/agent"
            class="block px-3 py-2 text-sm rounded-md"
            :class="route.path === '/settings/agent' ? 'bg-gray-100 text-gray-900 font-medium' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'"
          >
            Agent Configuration
          </router-link>
          <router-link
            to="/settings/tasks"
            class="block px-3 py-2 text-sm rounded-md"
            :class="route.path === '/settings/tasks' ? 'bg-gray-100 text-gray-900 font-medium' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'"
          >
            Task Management
          </router-link>
          <router-link
            to="/settings/security"
            class="block px-3 py-2 text-sm rounded-md"
            :class="route.path === '/settings/security' ? 'bg-gray-100 text-gray-900 font-medium' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'"
          >
            Security
          </router-link>
          <router-link
            to="/settings/integrations"
            class="block px-3 py-2 text-sm rounded-md"
            :class="route.path === '/settings/integrations' ? 'bg-gray-100 text-gray-900 font-medium' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'"
          >
            Integrations
          </router-link>
          <router-link
            to="/settings/users"
            class="block px-3 py-2 text-sm rounded-md"
            :class="route.path === '/settings/users' ? 'bg-gray-100 text-gray-900 font-medium' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'"
          >
            User Management
          </router-link>
        </div>
      </nav>

      <div class="flex-1 min-w-0">
        <router-view />
      </div>
    </div>
  </div>
</template>
