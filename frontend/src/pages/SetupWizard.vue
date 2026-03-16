<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { toast } from 'vue-sonner'

const auth = useAuthStore()
const router = useRouter()

const currentStep = ref(1)
const totalSteps = 3

// Step 1: Create Admin Account
const adminUsername = ref('')
const adminPassword = ref('')
const confirmPassword = ref('')
const step1Error = ref('')
const step1Loading = ref(false)

// Step 2: LLM Provider
const providerName = ref('default')
const providerUrl = ref('')
const apiKey = ref('')
const step2Error = ref('')
const step2Loading = ref(false)
const testingConnection = ref(false)
const connectionTested = ref(false)
const step2Success = ref('')
const providerUrlReadonly = ref(false)
const apiKeyReadonly = ref(false)
const providerId = ref<string | null>(null)

// Step 3: Model Selection
const models = ref<string[]>([])
const titleModel = ref('claude-haiku-4-5-20251001')
const taskModel = ref('claude-sonnet-4-5-20250929')
const step3Loading = ref(false)
const step3Error = ref('')

const passwordMismatch = computed(() =>
  confirmPassword.value !== '' && adminPassword.value !== confirmPassword.value
)

watch([providerName, providerUrl, apiKey], () => {
  connectionTested.value = false
  step2Success.value = ''
  // Reset provider if user changes fields (will be re-created on next test)
  if (!providerUrlReadonly.value) {
    providerId.value = null
  }
})

async function createAdmin() {
  step1Error.value = ''
  if (passwordMismatch.value) {
    step1Error.value = 'Passwords do not match.'
    return
  }
  if (adminPassword.value.length < 8) {
    step1Error.value = 'Password must be at least 8 characters.'
    return
  }
  step1Loading.value = true
  try {
    const resp = await fetch('/api/setup/create-user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: adminUsername.value, password: adminPassword.value }),
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      step1Error.value = data.detail || 'Failed to create admin account.'
      return
    }
    const data = await resp.json()
    auth.setToken(data.access_token)
    auth.setAuthMode('local')
    await loadLlmMetadata()
    currentStep.value = 2
  } catch {
    step1Error.value = 'Unable to connect. Please try again.'
  } finally {
    step1Loading.value = false
  }
}

async function loadLlmMetadata() {
  try {
    const resp = await fetch('/api/llm/providers', {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    if (resp.ok) {
      const providers = await resp.json()
      if (providers.length > 0) {
        const provider = providers[0]
        providerId.value = provider.id
        providerName.value = provider.name
        providerUrl.value = provider.base_url
        apiKey.value = provider.api_key
        // Lock all fields when an existing provider is found (env or database).
        // The wizard creates a new provider; editing belongs in the settings page.
        providerUrlReadonly.value = true
        apiKeyReadonly.value = true
      }
    }
  } catch {
    // Non-critical — user can fill in manually
  }
}

async function testConnection() {
  step2Error.value = ''
  step2Success.value = ''
  testingConnection.value = true
  let createdProviderId: string | null = null
  try {
    // If no existing provider, create one
    if (!providerId.value) {
      const createResp = await fetch('/api/llm/providers', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${auth.token}`,
        },
        body: JSON.stringify({
          name: providerName.value,
          base_url: providerUrl.value,
          api_key: apiKey.value,
        }),
      })
      if (!createResp.ok) {
        const data = await createResp.json().catch(() => ({}))
        step2Error.value = data.detail || 'Failed to create provider.'
        return
      }
      const provider = await createResp.json()
      createdProviderId = provider.id
      providerId.value = provider.id
    }
    // Test by fetching models from the provider
    const pid = providerId.value
    const resp = await fetch(`/api/llm/providers/${pid}/models`, {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
    if (!resp.ok) {
      // Clean up newly created provider on failure
      if (createdProviderId) {
        await fetch(`/api/llm/providers/${createdProviderId}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${auth.token}` },
        }).catch(() => {})
        providerId.value = null
      }
      step2Error.value = 'Connection failed. Check your URL and API key.'
      return
    }
    const data = await resp.json()
    models.value = data
    connectionTested.value = true
    step2Success.value = 'Connection successful'
    toast.success('Connection successful!')
  } catch {
    // Clean up newly created provider on failure
    if (createdProviderId) {
      await fetch(`/api/llm/providers/${createdProviderId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${auth.token}` },
      }).catch(() => {})
      providerId.value = null
    }
    step2Error.value = 'Connection failed. Check your URL and API key.'
  } finally {
    testingConnection.value = false
  }
}

async function advanceToStep3() {
  if (!connectionTested.value) {
    await testConnection()
    if (!connectionTested.value) return
  }
  currentStep.value = 3
  // If models haven't been loaded, try again
  if (models.value.length === 0 && providerId.value) {
    try {
      const resp = await fetch(`/api/llm/providers/${providerId.value}/models`, {
        headers: { Authorization: `Bearer ${auth.token}` },
      })
      if (resp.ok) {
        models.value = await resp.json()
      }
    } catch {
      // Use defaults
    }
  }
}

async function completeSetup() {
  step3Error.value = ''
  step3Loading.value = true
  try {
    const resp = await fetch('/api/settings', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        llm_model: { provider_id: providerId.value, model: titleModel.value },
        task_processing_model: { provider_id: providerId.value, model: taskModel.value },
      }),
    })
    if (!resp.ok) {
      step3Error.value = 'Failed to save model settings.'
      return
    }
    toast.success('Setup complete!')
    router.push('/settings')
  } catch {
    step3Error.value = 'Unable to save. Please try again.'
  } finally {
    step3Loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-100 flex items-start justify-center pt-16 px-4">
    <div class="max-w-xl w-full">
      <div class="text-center mb-8">
        <img src="/logo.png" alt="Logo" class="h-16 mx-auto mb-4" />
        <h1 class="text-2xl font-bold text-gray-900">Welcome to Errand</h1>
        <p class="text-sm text-gray-500 mt-1">Let's get you set up in a few steps.</p>
      </div>

      <!-- Step indicators -->
      <div class="flex items-center justify-center gap-2 mb-8" data-testid="setup-steps">
        <template v-for="step in totalSteps" :key="step">
          <div
            class="flex items-center justify-center h-8 w-8 rounded-full text-sm font-medium"
            :class="step === currentStep ? 'bg-gray-800 text-white' : step < currentStep ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'"
            :data-testid="`setup-step-${step}`"
          >
            <template v-if="step < currentStep">
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </template>
            <template v-else>{{ step }}</template>
          </div>
          <div v-if="step < totalSteps" class="w-12 h-0.5" :class="step < currentStep ? 'bg-green-500' : 'bg-gray-200'" />
        </template>
      </div>

      <!-- Step 1: Create Admin Account -->
      <div v-if="currentStep === 1" class="bg-white rounded-lg shadow p-8" data-testid="setup-step1">
        <h2 class="text-lg font-semibold text-gray-900 mb-1">Create Admin Account</h2>
        <p class="text-sm text-gray-500 mb-6">Set up your administrator credentials.</p>
        <form @submit.prevent="createAdmin" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700">Username</label>
            <input
              v-model="adminUsername"
              type="text"
              required
              autocomplete="username"
              data-testid="setup-username"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">Password</label>
            <input
              v-model="adminPassword"
              type="password"
              required
              autocomplete="new-password"
              data-testid="setup-password"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">Confirm Password</label>
            <input
              v-model="confirmPassword"
              type="password"
              required
              autocomplete="new-password"
              data-testid="setup-confirm-password"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
            />
            <p v-if="passwordMismatch" class="mt-1 text-sm text-red-600" data-testid="setup-password-mismatch">Passwords do not match.</p>
          </div>
          <div v-if="step1Error" class="text-sm text-red-600" data-testid="setup-step1-error">{{ step1Error }}</div>
          <button
            type="submit"
            :disabled="step1Loading"
            data-testid="setup-create-admin"
            class="w-full rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {{ step1Loading ? 'Creating...' : 'Create Account & Continue' }}
          </button>
        </form>
      </div>

      <!-- Step 2: LLM Provider -->
      <div v-if="currentStep === 2" class="bg-white rounded-lg shadow p-8" data-testid="setup-step2">
        <h2 class="text-lg font-semibold text-gray-900 mb-1">LLM Provider Configuration</h2>
        <p class="text-sm text-gray-500 mb-6">Configure your LLM provider (OpenAI-compatible API).</p>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700">Provider Name</label>
            <input
              v-model="providerName"
              type="text"
              placeholder="default"
              :disabled="providerUrlReadonly"
              data-testid="setup-provider-name"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 disabled:bg-gray-50 disabled:text-gray-500"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">Provider URL</label>
            <div class="relative">
              <input
                v-model="providerUrl"
                type="url"
                placeholder="https://api.openai.com/v1"
                :disabled="providerUrlReadonly"
                data-testid="setup-provider-url"
                class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 disabled:bg-gray-50 disabled:text-gray-500"
              />
              <div v-if="providerUrlReadonly" class="absolute right-2 top-1/2 -translate-y-1/2 mt-0.5" title="Set via environment variable">
                <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">API Key</label>
            <div class="relative">
              <input
                v-model="apiKey"
                type="password"
                placeholder="sk-..."
                :disabled="apiKeyReadonly"
                data-testid="setup-api-key"
                class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 disabled:bg-gray-50 disabled:text-gray-500"
              />
              <div v-if="apiKeyReadonly" class="absolute right-2 top-1/2 -translate-y-1/2 mt-0.5" title="Set via environment variable">
                <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
            </div>
          </div>
          <div v-if="step2Error" class="text-sm text-red-600" data-testid="setup-step2-error">{{ step2Error }}</div>
          <div v-if="step2Success" class="text-sm text-green-600" data-testid="setup-step2-success">{{ step2Success }}</div>
          <div class="flex gap-3">
            <button
              type="button"
              @click="testConnection"
              :disabled="testingConnection"
              data-testid="setup-test-connection"
              class="flex-1 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {{ testingConnection ? 'Testing...' : connectionTested ? 'Connection Verified \u2713' : 'Test Connection' }}
            </button>
            <button
              type="button"
              @click="advanceToStep3"
              :disabled="step2Loading"
              data-testid="setup-continue-step2"
              class="flex-1 rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              Continue
            </button>
          </div>
        </div>
      </div>

      <!-- Step 3: Model Selection -->
      <div v-if="currentStep === 3" class="bg-white rounded-lg shadow p-8" data-testid="setup-step3">
        <h2 class="text-lg font-semibold text-gray-900 mb-1">Model Selection</h2>
        <p class="text-sm text-gray-500 mb-6">Choose which models to use for different tasks.</p>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700">Title Generation Model</label>
            <select
              v-model="titleModel"
              data-testid="setup-title-model"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
            >
              <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
              <option v-if="!models.includes(titleModel)" :value="titleModel">{{ titleModel }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700">Default Task Model</label>
            <select
              v-model="taskModel"
              data-testid="setup-task-model"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
            >
              <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
              <option v-if="!models.includes(taskModel)" :value="taskModel">{{ taskModel }}</option>
            </select>
          </div>
          <div v-if="step3Error" class="text-sm text-red-600" data-testid="setup-step3-error">{{ step3Error }}</div>
          <button
            type="button"
            @click="completeSetup"
            :disabled="step3Loading"
            data-testid="setup-complete"
            class="w-full rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {{ step3Loading ? 'Saving...' : 'Complete Setup' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
