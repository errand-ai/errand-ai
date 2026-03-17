<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { fetchTaskProfiles, type TaskProfile } from '../../composables/useApi'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()

interface TaskGeneratorData {
  id: string
  type: string
  enabled: boolean
  profile_id: string | null
  config: Record<string, any> | null
  created_at: string
  updated_at: string
}

const loading = ref(true)
const saving = ref(false)
const error = ref<string | null>(null)

// Email generator state
const emailGenerator = ref<TaskGeneratorData | null>(null)
const emailEnabled = ref(false)
const emailProfileId = ref('')
const emailPollInterval = ref('60')
const emailTaskPrompt = ref('')
const emailCredentialsConfigured = ref(false)

// Profiles for dropdown
const profiles = ref<TaskProfile[]>([])

// Validation
const pollIntervalError = ref<string | null>(null)

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

async function loadData() {
  loading.value = true
  error.value = null
  try {
    // Load profiles and email generator in parallel
    const [profilesResult, generatorResult, platformsResult] = await Promise.all([
      fetchTaskProfiles().catch(() => [] as TaskProfile[]),
      authFetch('/api/task-generators/email').then(r => r.ok ? r.json() : null).catch(() => null),
      authFetch('/api/platforms').then(r => r.ok ? r.json() : []).catch(() => []),
    ])

    profiles.value = profilesResult
    emailGenerator.value = generatorResult

    // Check if email credentials are configured
    const emailPlatform = platformsResult.find((p: any) => p.id === 'email')
    emailCredentialsConfigured.value = emailPlatform?.status === 'connected'

    // Populate form from loaded data
    if (generatorResult) {
      emailEnabled.value = generatorResult.enabled
      emailProfileId.value = generatorResult.profile_id || ''
      const config = generatorResult.config || {}
      emailPollInterval.value = String(config.poll_interval || 60)
      emailTaskPrompt.value = config.task_prompt || ''
    }
  } catch {
    error.value = 'Failed to load task generator settings.'
  } finally {
    loading.value = false
  }
}

function validatePollInterval(): boolean {
  const val = parseInt(emailPollInterval.value, 10)
  if (isNaN(val) || val < 60) {
    pollIntervalError.value = 'Minimum poll interval is 60 seconds.'
    return false
  }
  pollIntervalError.value = null
  return true
}

async function saveEmailGenerator() {
  if (!validatePollInterval()) return

  saving.value = true
  try {
    const config: Record<string, any> = {}
    const pollVal = parseInt(emailPollInterval.value, 10)
    if (!isNaN(pollVal)) config.poll_interval = pollVal
    if (emailTaskPrompt.value.trim()) config.task_prompt = emailTaskPrompt.value.trim()

    const body: Record<string, any> = {
      enabled: emailEnabled.value,
      profile_id: emailProfileId.value || null,
      config,
    }

    const res = await authFetch('/api/task-generators/email', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })

    if (!res.ok) throw new Error(`Failed to save (HTTP ${res.status})`)

    emailGenerator.value = await res.json()
    toast.success('Email trigger settings saved.')
  } catch {
    toast.error('Failed to save email trigger settings.')
  } finally {
    saving.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div>
    <div v-if="loading" class="text-sm text-gray-500">Loading task generators...</div>

    <div v-else-if="error" class="text-sm text-red-600">{{ error }}</div>

    <div v-else>
      <!-- Email Trigger Card -->
      <div class="rounded-lg bg-white p-6 shadow" data-testid="email-trigger-card">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-gray-800">Email Trigger</h3>
          <label class="relative inline-flex items-center cursor-pointer" data-testid="email-enabled-toggle">
            <input
              type="checkbox"
              v-model="emailEnabled"
              class="sr-only peer"
              :disabled="!emailCredentialsConfigured"
            />
            <div class="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600 peer-disabled:opacity-50"></div>
            <span class="ml-2 text-sm text-gray-600">{{ emailEnabled ? 'Enabled' : 'Disabled' }}</span>
          </label>
        </div>

        <p class="text-sm text-gray-500 mb-4">
          Automatically create tasks from incoming emails.
        </p>

        <!-- No email credentials warning -->
        <div
          v-if="!emailCredentialsConfigured"
          class="rounded-md bg-yellow-50 border border-yellow-200 p-3 text-sm text-yellow-800 mb-4"
          data-testid="email-no-credentials"
        >
          Email credentials are not configured. Please set up email credentials in
          <router-link to="/settings/integrations" class="font-medium underline">Integrations</router-link>
          first.
        </div>

        <template v-if="emailCredentialsConfigured">
          <div class="space-y-4">
            <!-- Task Profile Selector -->
            <div>
              <label for="email-profile" class="block text-sm font-medium text-gray-700 mb-1">Task Profile</label>
              <select
                id="email-profile"
                v-model="emailProfileId"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                data-testid="email-profile-select"
              >
                <option value="">Default</option>
                <option v-for="profile in profiles" :key="profile.id" :value="profile.id">
                  {{ profile.name }}
                </option>
              </select>
            </div>

            <!-- Poll Interval -->
            <div>
              <label for="email-poll-interval" class="block text-sm font-medium text-gray-700 mb-1">
                Poll Interval (seconds)
              </label>
              <input
                id="email-poll-interval"
                v-model="emailPollInterval"
                type="number"
                min="60"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                :class="{ 'border-red-300': pollIntervalError }"
                data-testid="email-poll-interval"
                @input="validatePollInterval"
              />
              <p v-if="pollIntervalError" class="mt-1 text-xs text-red-500" data-testid="poll-interval-error">
                {{ pollIntervalError }}
              </p>
              <p class="mt-1 text-xs text-gray-500">
                Minimum 60 seconds. Reduced when IMAP IDLE is supported. Changes take effect after the current poll cycle.
              </p>
            </div>

            <!-- Task Prompt -->
            <div>
              <label for="email-task-prompt" class="block text-sm font-medium text-gray-700 mb-1">
                Task Prompt
              </label>
              <textarea
                id="email-task-prompt"
                v-model="emailTaskPrompt"
                rows="4"
                class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                placeholder="Optional instructions appended to email-triggered tasks..."
                data-testid="email-task-prompt"
              ></textarea>
              <p class="mt-1 text-xs text-gray-500">
                Additional instructions appended to the task description for the LLM agent.
              </p>
            </div>

            <!-- Save Button -->
            <button
              @click="saveEmailGenerator"
              :disabled="saving"
              class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              data-testid="email-save"
            >
              {{ saving ? 'Saving...' : 'Save' }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
