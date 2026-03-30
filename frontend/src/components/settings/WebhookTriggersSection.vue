<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchWebhookTriggers,
  createWebhookTrigger,
  updateWebhookTrigger,
  deleteWebhookTrigger,
  fetchTaskProfiles,
  fetchJiraCredentialStatus,
  type WebhookTrigger,
  type TaskProfile,
} from '../../composables/useApi'

const loading = ref(true)
const triggers = ref<WebhookTrigger[]>([])
const profiles = ref<TaskProfile[]>([])
const jiraConnected = ref(false)

// Form state
const showForm = ref(false)
const editingId = ref<string | null>(null)
const editingTrigger = ref<WebhookTrigger | null>(null)
const saving = ref(false)

const formName = ref('')
const formSource = ref('jira')
const formEnabled = ref(true)
const formProfileId = ref('')
const formTaskPrompt = ref('')
const formWebhookSecret = ref('')
const formSecretSaved = ref(false)

// Filters
const formEventTypes = ref<string[]>([])
const formIssueTypes = ref<string[]>([])
const formLabels = ref('')
const formProjects = ref('')

// Actions
const formAssignTo = ref(false)
const formAddComment = ref(false)
const formAddLabel = ref('')
const formTransitionOnComplete = ref('')
const formCommentOutput = ref(false)

// Delete confirmation
const showDeleteConfirm = ref(false)
const deleteTargetId = ref<string | null>(null)
const deleteTargetName = ref('')

// Validation
const nameError = ref<string | null>(null)

const JIRA_EVENT_TYPES = ['jira:issue_created', 'jira:issue_updated']
const JIRA_ISSUE_TYPES = ['Task', 'Story', 'Bug', 'Feature', 'Epic']

const isEditing = computed(() => editingId.value !== null)

async function loadData() {
  loading.value = true
  try {
    const [triggersResult, profilesResult, jiraStatus] = await Promise.all([
      fetchWebhookTriggers().catch(() => []),
      fetchTaskProfiles().catch(() => []),
      fetchJiraCredentialStatus().catch(() => ({ status: 'disconnected' })),
    ])
    triggers.value = triggersResult
    profiles.value = profilesResult
    jiraConnected.value = jiraStatus.status === 'connected'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  editingTrigger.value = null
  formName.value = ''
  formSource.value = 'jira'
  formEnabled.value = true
  formProfileId.value = ''
  formTaskPrompt.value = ''
  formWebhookSecret.value = ''
  formSecretSaved.value = false
  formEventTypes.value = []
  formIssueTypes.value = []
  formLabels.value = ''
  formProjects.value = ''
  formAssignTo.value = false
  formAddComment.value = false
  formAddLabel.value = ''
  formTransitionOnComplete.value = ''
  formCommentOutput.value = false
  nameError.value = null
}

function openCreate() {
  resetForm()
  showForm.value = true
}

function openEdit(trigger: WebhookTrigger) {
  editingId.value = trigger.id
  editingTrigger.value = trigger
  formName.value = trigger.name
  formSource.value = trigger.source
  formEnabled.value = trigger.enabled
  formProfileId.value = trigger.profile_id || ''
  formTaskPrompt.value = trigger.task_prompt || ''
  formWebhookSecret.value = ''
  formSecretSaved.value = trigger.has_secret

  // Filters
  formEventTypes.value = trigger.filters?.event_types || []
  formIssueTypes.value = trigger.filters?.issue_types || []
  formLabels.value = (trigger.filters?.labels || []).join(', ')
  formProjects.value = (trigger.filters?.projects || []).join(', ')

  // Actions
  const actions = trigger.actions || {}
  formAssignTo.value = !!actions.assign_to
  formAddComment.value = !!actions.add_comment
  formAddLabel.value = typeof actions.add_label === 'string' ? actions.add_label : ''
  formTransitionOnComplete.value = typeof actions.transition_on_complete === 'string' ? actions.transition_on_complete : ''
  formCommentOutput.value = !!actions.comment_output

  nameError.value = null
  showForm.value = true
}

function buildFilters(): Record<string, string[]> {
  const filters: Record<string, string[]> = {}
  if (formEventTypes.value.length) filters.event_types = formEventTypes.value
  if (formIssueTypes.value.length) filters.issue_types = formIssueTypes.value
  const labels = formLabels.value.split(',').map((s) => s.trim()).filter(Boolean)
  if (labels.length) filters.labels = labels
  const projects = formProjects.value.split(',').map((s) => s.trim()).filter(Boolean)
  if (projects.length) filters.projects = projects
  return filters
}

function buildActions(): Record<string, string | boolean> {
  const actions: Record<string, string | boolean> = {}
  if (formAssignTo.value) actions.assign_to = 'service_account'
  if (formAddComment.value) actions.add_comment = true
  if (formAddLabel.value.trim()) actions.add_label = formAddLabel.value.trim()
  if (formTransitionOnComplete.value.trim()) actions.transition_on_complete = formTransitionOnComplete.value.trim()
  if (formCommentOutput.value) actions.comment_output = true
  return actions
}

function validate(): boolean {
  nameError.value = null
  if (!formName.value.trim()) {
    nameError.value = 'Name is required'
    return false
  }
  return true
}

function generateSecret() {
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  formWebhookSecret.value = Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('')
}

async function save() {
  if (!validate()) return
  saving.value = true
  try {
    const data: any = {
      name: formName.value.trim(),
      source: formSource.value,
      enabled: formEnabled.value,
      profile_id: formProfileId.value || null,
      filters: buildFilters(),
      actions: buildActions(),
      task_prompt: formTaskPrompt.value.trim() || null,
    }
    if (formWebhookSecret.value) data.webhook_secret = formWebhookSecret.value

    if (isEditing.value) {
      await updateWebhookTrigger(editingId.value!, data)
      toast.success('Trigger updated')
    } else {
      await createWebhookTrigger(data)
      toast.success('Trigger created')
    }

    showForm.value = false
    resetForm()
    await loadData()
  } catch (err: any) {
    toast.error(err.message || 'Failed to save trigger')
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(trigger: WebhookTrigger) {
  try {
    await updateWebhookTrigger(trigger.id, { enabled: !trigger.enabled })
    trigger.enabled = !trigger.enabled
  } catch {
    toast.error('Failed to update trigger')
  }
}

function confirmDelete(trigger: WebhookTrigger) {
  deleteTargetId.value = trigger.id
  deleteTargetName.value = trigger.name
  showDeleteConfirm.value = true
}

async function executeDelete() {
  if (!deleteTargetId.value) return
  try {
    await deleteWebhookTrigger(deleteTargetId.value)
    toast.success('Trigger deleted')
    showDeleteConfirm.value = false
    showForm.value = false
    resetForm()
    await loadData()
  } catch {
    toast.error('Failed to delete trigger')
  }
}

function toggleEventType(event: string) {
  const idx = formEventTypes.value.indexOf(event)
  if (idx >= 0) formEventTypes.value.splice(idx, 1)
  else formEventTypes.value.push(event)
}

function toggleIssueType(type: string) {
  const idx = formIssueTypes.value.indexOf(type)
  if (idx >= 0) formIssueTypes.value.splice(idx, 1)
  else formIssueTypes.value.push(type)
}

onMounted(loadData)
</script>

<template>
  <div class="mt-6 rounded-lg bg-white p-6 shadow" data-testid="webhook-triggers-section">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-gray-800">Webhook Triggers</h3>
      <button
        @click="openCreate"
        :disabled="!jiraConnected"
        class="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        data-testid="add-trigger-btn"
      >
        Add Trigger
      </button>
    </div>

    <p class="text-sm text-gray-500 mb-4">
      Automatically create tasks from incoming webhooks (e.g. Jira issues).
    </p>

    <div
      v-if="!jiraConnected"
      class="rounded-md bg-yellow-50 border border-yellow-200 p-3 text-sm text-yellow-800 mb-4"
      data-testid="jira-no-credentials"
    >
      Jira credentials are not configured. Please set up Jira credentials in
      <router-link to="/settings/integrations" class="font-medium underline">Integrations</router-link>
      first.
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-gray-500">Loading triggers...</div>

    <!-- Triggers list -->
    <div v-else-if="triggers.length && !showForm">
      <div class="divide-y divide-gray-200">
        <div
          v-for="trigger in triggers"
          :key="trigger.id"
          class="flex items-center justify-between py-3 cursor-pointer hover:bg-gray-50 -mx-2 px-2 rounded"
          data-testid="trigger-row"
          @click="openEdit(trigger)"
        >
          <div class="flex items-center gap-3">
            <span class="text-sm font-medium text-gray-800">{{ trigger.name }}</span>
            <span class="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{{ trigger.source }}</span>
          </div>
          <div class="flex items-center gap-3" @click.stop>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                :checked="trigger.enabled"
                class="sr-only peer"
                @change="toggleEnabled(trigger)"
                :data-testid="`trigger-toggle-${trigger.id}`"
              />
              <div class="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!triggers.length && !showForm && jiraConnected" class="text-sm text-gray-500" data-testid="no-triggers">
      No webhook triggers configured.
    </div>

    <!-- Create/Edit Form -->
    <div v-if="showForm" class="space-y-4 mt-4" data-testid="trigger-form">
      <h4 class="text-sm font-semibold text-gray-700">
        {{ isEditing ? 'Edit Trigger' : 'New Trigger' }}
      </h4>

      <!-- Source -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Source</label>
        <select
          v-model="formSource"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          :disabled="isEditing"
          data-testid="trigger-source"
        >
          <option value="jira">Jira</option>
        </select>
      </div>

      <!-- Name -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Name</label>
        <input
          v-model="formName"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          :class="{ 'border-red-300': nameError }"
          placeholder="e.g. Jira Bugs"
          data-testid="trigger-name"
        />
        <p v-if="nameError" class="mt-1 text-xs text-red-500" data-testid="name-error">{{ nameError }}</p>
      </div>

      <!-- Profile -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Task Profile</label>
        <select
          v-model="formProfileId"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          data-testid="trigger-profile"
        >
          <option value="">Default</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>

      <!-- Jira Filters -->
      <div v-if="formSource === 'jira'" class="space-y-3 rounded-md border border-gray-200 p-4">
        <h5 class="text-sm font-medium text-gray-700">Filters</h5>
        <p class="text-xs text-gray-500">Leave empty to match all. Filters are ANDed together.</p>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Event Types</label>
          <div class="flex gap-2 flex-wrap">
            <label
              v-for="evt in JIRA_EVENT_TYPES"
              :key="evt"
              class="inline-flex items-center gap-1 text-xs"
            >
              <input
                type="checkbox"
                :checked="formEventTypes.includes(evt)"
                @change="toggleEventType(evt)"
                class="rounded border-gray-300"
              />
              {{ evt }}
            </label>
          </div>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Issue Types</label>
          <div class="flex gap-2 flex-wrap">
            <label
              v-for="it in JIRA_ISSUE_TYPES"
              :key="it"
              class="inline-flex items-center gap-1 text-xs"
            >
              <input
                type="checkbox"
                :checked="formIssueTypes.includes(it)"
                @change="toggleIssueType(it)"
                class="rounded border-gray-300"
              />
              {{ it }}
            </label>
          </div>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Labels (comma-separated)</label>
          <input
            v-model="formLabels"
            type="text"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="e.g. errand, automation"
            data-testid="trigger-labels"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Projects (comma-separated)</label>
          <input
            v-model="formProjects"
            type="text"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="e.g. PROJ, WEBAPP"
            data-testid="trigger-projects"
          />
        </div>
      </div>

      <!-- Actions -->
      <div class="space-y-3 rounded-md border border-gray-200 p-4">
        <h5 class="text-sm font-medium text-gray-700">Completion Actions</h5>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" v-model="formAssignTo" class="rounded border-gray-300" />
          Assign to service account
        </label>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" v-model="formAddComment" class="rounded border-gray-300" />
          Add comment with task reference
        </label>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" v-model="formCommentOutput" class="rounded border-gray-300" />
          Comment output on complete
        </label>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Add label on complete</label>
          <input
            v-model="formAddLabel"
            type="text"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="e.g. errand-done"
            data-testid="trigger-add-label"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Transition on complete</label>
          <input
            v-model="formTransitionOnComplete"
            type="text"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="e.g. Done"
            data-testid="trigger-transition"
          />
        </div>
      </div>

      <!-- Task Prompt -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Task Prompt</label>
        <textarea
          v-model="formTaskPrompt"
          rows="3"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono"
          placeholder="Optional instructions for the LLM agent..."
          data-testid="trigger-task-prompt"
        ></textarea>
      </div>

      <!-- Webhook Secret -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Webhook Secret</label>
        <div class="flex gap-2">
          <input
            v-model="formWebhookSecret"
            type="text"
            class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm font-mono"
            :placeholder="formSecretSaved ? '****...saved (enter new to replace)' : 'Paste or generate a secret'"
            data-testid="trigger-secret"
          />
          <button
            @click="generateSecret"
            type="button"
            class="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
            data-testid="generate-secret-btn"
          >
            Generate
          </button>
        </div>
      </div>

      <!-- Form buttons -->
      <div class="flex items-center gap-2 pt-2">
        <button
          @click="save"
          :disabled="saving"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          data-testid="trigger-save-btn"
        >
          {{ saving ? 'Saving...' : 'Save' }}
        </button>
        <button
          @click="showForm = false; resetForm()"
          class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          data-testid="trigger-cancel-btn"
        >
          Cancel
        </button>
        <button
          v-if="isEditing"
          @click="editingTrigger && confirmDelete(editingTrigger)"
          class="ml-auto rounded-md border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50"
          data-testid="trigger-delete-btn"
        >
          Delete
        </button>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div v-if="showDeleteConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" data-testid="delete-confirm-modal">
      <div class="rounded-lg bg-white p-6 shadow-xl max-w-sm w-full mx-4">
        <h4 class="text-lg font-semibold text-gray-800 mb-2">Delete Trigger</h4>
        <p class="text-sm text-gray-600 mb-4">
          Are you sure you want to delete <strong>{{ deleteTargetName }}</strong>? This is permanent and any webhooks configured in external systems will stop working.
        </p>
        <div class="flex justify-end gap-2">
          <button
            @click="showDeleteConfirm = false"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            data-testid="delete-cancel-btn"
          >
            Cancel
          </button>
          <button
            @click="executeDelete"
            class="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            data-testid="delete-confirm-btn"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
