<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchJiraCredentialStatus,
  saveJiraCredentials,
  deleteJiraCredentials,
  type JiraCredentialStatus,
} from '../../composables/useApi'

const loading = ref(true)
const saving = ref(false)
const status = ref<JiraCredentialStatus | null>(null)
const showForm = ref(false)
const showDisconnectConfirm = ref(false)

// Form fields
const cloudId = ref('')
const apiToken = ref('')
const siteUrl = ref('')
const serviceAccountEmail = ref('')
const formError = ref<string | null>(null)

async function loadStatus() {
  loading.value = true
  try {
    status.value = await fetchJiraCredentialStatus()
  } catch {
    status.value = null
  } finally {
    loading.value = false
  }
}

async function save() {
  formError.value = null
  if (!cloudId.value.trim() || !apiToken.value.trim() || !siteUrl.value.trim() || !serviceAccountEmail.value.trim()) {
    formError.value = 'All fields are required'
    return
  }

  saving.value = true
  try {
    status.value = await saveJiraCredentials({
      cloud_id: cloudId.value.trim(),
      api_token: apiToken.value.trim(),
      site_url: siteUrl.value.trim(),
      service_account_email: serviceAccountEmail.value.trim(),
    })
    showForm.value = false
    cloudId.value = ''
    apiToken.value = ''
    siteUrl.value = ''
    serviceAccountEmail.value = ''
    toast.success('Jira credentials saved and verified')
  } catch (err: any) {
    formError.value = err.message || 'Failed to save Jira credentials'
  } finally {
    saving.value = false
  }
}

async function disconnect() {
  try {
    await deleteJiraCredentials()
    status.value = { platform_id: 'jira', status: 'disconnected', site_url: null, last_verified_at: null }
    showDisconnectConfirm.value = false
    toast.success('Jira credentials removed')
  } catch {
    toast.error('Failed to remove Jira credentials')
  }
}

onMounted(loadStatus)
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="jira-credential-card">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-gray-800">Jira</h3>
      <span
        v-if="!loading"
        :class="status?.status === 'connected' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'"
        class="px-2 py-0.5 rounded text-xs font-medium"
        data-testid="jira-status-badge"
      >
        {{ status?.status === 'connected' ? 'Connected' : 'Not Connected' }}
      </span>
    </div>

    <div v-if="loading" class="text-sm text-gray-500">Loading...</div>

    <div v-else>
      <!-- Connected state -->
      <div v-if="status?.status === 'connected'" class="space-y-2">
        <p class="text-sm text-gray-600">
          Site: <span class="font-medium">{{ status.site_url }}</span>
        </p>
        <p v-if="status.last_verified_at" class="text-xs text-gray-500">
          Verified: {{ new Date(status.last_verified_at).toLocaleString() }}
        </p>
        <div class="flex gap-2 mt-3">
          <button
            @click="showForm = true"
            class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            data-testid="jira-reconfigure-btn"
          >
            Reconfigure
          </button>
          <button
            @click="showDisconnectConfirm = true"
            class="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
            data-testid="jira-disconnect-btn"
          >
            Disconnect
          </button>
        </div>
      </div>

      <!-- Not connected -->
      <div v-else>
        <p class="text-sm text-gray-500 mb-3">
          Connect your Jira Cloud instance to enable webhook triggers.
        </p>
        <button
          @click="showForm = true"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          data-testid="jira-connect-btn"
        >
          Connect Jira
        </button>
      </div>

      <!-- Connection form -->
      <div v-if="showForm" class="mt-4 space-y-3 rounded-md border border-gray-200 p-4" data-testid="jira-form">
        <div v-if="formError" class="text-sm text-red-600" data-testid="jira-form-error">{{ formError }}</div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Site URL</label>
          <input
            v-model="siteUrl"
            type="url"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="https://your-org.atlassian.net"
            data-testid="jira-site-url"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Cloud ID</label>
          <input
            v-model="cloudId"
            type="text"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Your Atlassian Cloud ID"
            data-testid="jira-cloud-id"
          />
          <p class="text-xs text-gray-500 mt-1">Found at _edge/tenant_info on your Atlassian domain.</p>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">API Token</label>
          <input
            v-model="apiToken"
            type="password"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Atlassian API token"
            data-testid="jira-api-token"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Service Account Email</label>
          <input
            v-model="serviceAccountEmail"
            type="email"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="bot@your-org.com"
            data-testid="jira-service-account"
          />
        </div>

        <div class="flex gap-2 pt-2">
          <button
            @click="save"
            :disabled="saving"
            class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            data-testid="jira-save-btn"
          >
            {{ saving ? 'Verifying...' : 'Save & Verify' }}
          </button>
          <button
            @click="showForm = false; formError = null"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Disconnect Confirmation -->
    <div v-if="showDisconnectConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" data-testid="jira-disconnect-modal">
      <div class="rounded-lg bg-white p-6 shadow-xl max-w-sm w-full mx-4">
        <h4 class="text-lg font-semibold text-gray-800 mb-2">Disconnect Jira</h4>
        <p class="text-sm text-gray-600 mb-4">
          This will remove your Jira credentials. Existing webhook triggers will stop receiving updates from Jira.
        </p>
        <div class="flex justify-end gap-2">
          <button
            @click="showDisconnectConfirm = false"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            @click="disconnect"
            class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            data-testid="jira-disconnect-confirm-btn"
          >
            Disconnect
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
