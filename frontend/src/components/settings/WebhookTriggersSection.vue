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
  fetchGithubCredentialStatus,
  introspectGithubProject,
  type WebhookTrigger,
  type TaskProfile,
} from '../../composables/useApi'

const loading = ref(true)
const triggers = ref<WebhookTrigger[]>([])
const profiles = ref<TaskProfile[]>([])
const jiraConnected = ref(false)
const githubConnected = ref(false)

// GitHub-specific state
const formGithubOrg = ref('')
const formGithubProjectNumber = ref<number | null>(null)
const formProjectNodeId = ref('')
const formTriggerColumn = ref('')
const formContentTypes = ref<string[]>(['Issue'])
const formColumnOnRunning = ref('')
const formColumnOnComplete = ref('')
const formCopilotReview = ref(false)
const formReviewProfileId = ref('')
const formProjectFieldId = ref('')
const formColumnOptions = ref<Record<string, string>>({})
const introspecting = ref(false)
const introspectError = ref('')
const statusOptions = ref<Array<{id: string, name: string}>>([])

const GITHUB_CONTENT_TYPES = ['Issue', 'PullRequest', 'DraftIssue']

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
    const [triggersResult, profilesResult, jiraStatus, githubStatus] = await Promise.all([
      fetchWebhookTriggers().catch(() => []),
      fetchTaskProfiles().catch(() => []),
      fetchJiraCredentialStatus().catch(() => ({ status: 'disconnected' })),
      fetchGithubCredentialStatus().catch(() => ({ status: 'disconnected' })),
    ])
    triggers.value = triggersResult
    profiles.value = profilesResult
    jiraConnected.value = jiraStatus.status === 'connected'
    githubConnected.value = githubStatus.status === 'connected'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  editingTrigger.value = null
  formName.value = ''
  // Default to the first connected integration so users can't land on a form
  // backed by disconnected credentials. Fall back to 'jira' when neither is
  // connected (the Add Trigger button is disabled in that state anyway).
  formSource.value = jiraConnected.value ? 'jira' : (githubConnected.value ? 'github' : 'jira')
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
  formGithubOrg.value = ''
  formGithubProjectNumber.value = null
  formProjectNodeId.value = ''
  formTriggerColumn.value = ''
  formContentTypes.value = ['Issue']
  formColumnOnRunning.value = ''
  formColumnOnComplete.value = ''
  formCopilotReview.value = false
  formReviewProfileId.value = ''
  formProjectFieldId.value = ''
  formColumnOptions.value = {}
  introspectError.value = ''
  statusOptions.value = []
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

  if (trigger.source === 'github') {
    formProjectNodeId.value = trigger.filters?.project_node_id || ''
    formTriggerColumn.value = trigger.filters?.trigger_column || ''
    formContentTypes.value = trigger.filters?.content_types || ['Issue']
    formColumnOnRunning.value = typeof actions.column_on_running === 'string' ? actions.column_on_running : ''
    formColumnOnComplete.value = typeof actions.column_on_complete === 'string' ? actions.column_on_complete : ''
    formCopilotReview.value = !!actions.copilot_review
    formReviewProfileId.value = typeof actions.review_profile_id === 'string' ? actions.review_profile_id : ''
    formProjectFieldId.value = typeof actions.project_field_id === 'string' ? actions.project_field_id : ''
    formColumnOptions.value = actions.column_options || {}
    if (actions.column_options) {
      statusOptions.value = Object.entries(actions.column_options).map(([name, id]) => ({ id: id as string, name }))
    }
  }

  nameError.value = null
  showForm.value = true
}

function buildFilters(): Record<string, any> {
  if (formSource.value === 'github') {
    const filters: Record<string, any> = {
      project_node_id: formProjectNodeId.value,
      trigger_column: formTriggerColumn.value,
    }
    if (formContentTypes.value.length) filters.content_types = formContentTypes.value
    return filters
  }
  const filters: Record<string, string[]> = {}
  if (formEventTypes.value.length) filters.event_types = formEventTypes.value
  if (formIssueTypes.value.length) filters.issue_types = formIssueTypes.value
  const labels = formLabels.value.split(',').map((s) => s.trim()).filter(Boolean)
  if (labels.length) filters.labels = labels
  const projects = formProjects.value.split(',').map((s) => s.trim()).filter(Boolean)
  if (projects.length) filters.projects = projects
  return filters
}

function buildActions(): Record<string, any> {
  if (formSource.value === 'github') {
    const actions: Record<string, any> = {}
    if (formAddComment.value) actions.add_comment = true
    if (formCommentOutput.value) actions.comment_output = true
    if (formColumnOnRunning.value) actions.column_on_running = formColumnOnRunning.value
    if (formColumnOnComplete.value) actions.column_on_complete = formColumnOnComplete.value
    if (formCopilotReview.value) actions.copilot_review = true
    if (formReviewProfileId.value) actions.review_profile_id = formReviewProfileId.value
    if (formProjectFieldId.value) actions.project_field_id = formProjectFieldId.value
    if (Object.keys(formColumnOptions.value).length) actions.column_options = formColumnOptions.value
    return actions
  }
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

async function introspectProject() {
  if (!formGithubOrg.value || !formGithubProjectNumber.value) return
  introspecting.value = true
  introspectError.value = ''
  try {
    const result = await introspectGithubProject(formGithubOrg.value, formGithubProjectNumber.value)
    formProjectNodeId.value = result.project_node_id
    if (result.status_field) {
      formProjectFieldId.value = result.status_field.field_id
      statusOptions.value = result.status_field.options
      const opts: Record<string, string> = {}
      for (const opt of result.status_field.options) {
        opts[opt.name] = opt.id
      }
      formColumnOptions.value = opts
    }
    toast.success(`Project "${result.title}" introspected`)
  } catch (err: any) {
    introspectError.value = err.message || 'Failed to introspect project'
    toast.error(introspectError.value)
  } finally {
    introspecting.value = false
  }
}

function toggleContentType(ct: string) {
  const idx = formContentTypes.value.indexOf(ct)
  if (idx >= 0) formContentTypes.value.splice(idx, 1)
  else formContentTypes.value.push(ct)
}

onMounted(loadData)
</script>

<template>
  <div class="mt-6 rounded-lg bg-white p-6 shadow" data-testid="webhook-triggers-section">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-gray-800">Webhook Triggers</h3>
      <button
        @click="openCreate"
        :disabled="!jiraConnected && !githubConnected"
        class="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        data-testid="add-trigger-btn"
      >
        Add Trigger
      </button>
    </div>

    <p class="text-sm text-gray-500 mb-4">
      Automatically create tasks from incoming webhooks (e.g. Jira issues, GitHub Projects).
    </p>

    <div
      v-if="!jiraConnected && !githubConnected"
      class="rounded-md bg-yellow-50 border border-yellow-200 p-3 text-sm text-yellow-800 mb-4"
      data-testid="no-credentials"
    >
      No integration credentials configured. Set up Jira or GitHub credentials in
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
    <div v-else-if="!triggers.length && !showForm && (jiraConnected || githubConnected)" class="text-sm text-gray-500" data-testid="no-triggers">
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
          <option value="github">GitHub</option>
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

      <!-- GitHub Filters -->
      <div v-if="formSource === 'github'" class="space-y-3 rounded-md border border-gray-200 p-4">
        <h5 class="text-sm font-medium text-gray-700">GitHub Project</h5>

        <div class="flex gap-2 items-end">
          <div class="flex-1">
            <label class="block text-xs font-medium text-gray-600 mb-1">Organization</label>
            <input v-model="formGithubOrg" type="text" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="e.g. acme-corp" data-testid="github-org" />
          </div>
          <div class="w-32">
            <label class="block text-xs font-medium text-gray-600 mb-1">Project #</label>
            <input v-model.number="formGithubProjectNumber" type="number" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" placeholder="e.g. 5" data-testid="github-project-number" />
          </div>
          <button @click="introspectProject" :disabled="introspecting || !formGithubOrg || !formGithubProjectNumber" type="button" class="rounded-md bg-gray-100 border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50" data-testid="introspect-btn">
            {{ introspecting ? 'Loading...' : 'Introspect' }}
          </button>
        </div>
        <p v-if="introspectError" class="text-xs text-red-500">{{ introspectError }}</p>
        <p v-if="formProjectNodeId" class="text-xs text-green-600">Project: {{ formProjectNodeId }}</p>

        <div v-if="statusOptions.length">
          <label class="block text-xs font-medium text-gray-600 mb-1">Trigger Column (creates task when issue moves here)</label>
          <select v-model="formTriggerColumn" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" data-testid="github-trigger-column">
            <option value="">Select column...</option>
            <option v-for="opt in statusOptions" :key="opt.id" :value="opt.name">{{ opt.name }}</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Content Types</label>
          <div class="flex gap-2 flex-wrap">
            <label v-for="ct in GITHUB_CONTENT_TYPES" :key="ct" class="inline-flex items-center gap-1 text-xs">
              <input type="checkbox" :checked="formContentTypes.includes(ct)" @change="toggleContentType(ct)" class="rounded border-gray-300" />
              {{ ct }}
            </label>
          </div>
        </div>
      </div>

      <!-- Jira Actions -->
      <div v-if="formSource === 'jira'" class="space-y-3 rounded-md border border-gray-200 p-4">
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

      <!-- GitHub Actions -->
      <div v-if="formSource === 'github'" class="space-y-3 rounded-md border border-gray-200 p-4">
        <h5 class="text-sm font-medium text-gray-700">Actions</h5>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" v-model="formAddComment" class="rounded border-gray-300" />
          Post comments on issue (task started, completed, failed)
        </label>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" v-model="formCommentOutput" class="rounded border-gray-300" />
          Include task output in completion comment
        </label>

        <div v-if="statusOptions.length">
          <label class="block text-xs font-medium text-gray-600 mb-1">Column on Running</label>
          <select v-model="formColumnOnRunning" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" data-testid="github-column-running">
            <option value="">None</option>
            <option v-for="opt in statusOptions" :key="opt.id" :value="opt.name">{{ opt.name }}</option>
          </select>
        </div>

        <div v-if="statusOptions.length">
          <label class="block text-xs font-medium text-gray-600 mb-1">Column on Complete</label>
          <select v-model="formColumnOnComplete" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" data-testid="github-column-complete">
            <option value="">None</option>
            <option v-for="opt in statusOptions" :key="opt.id" :value="opt.name">{{ opt.name }}</option>
          </select>
        </div>

        <label class="flex items-center gap-2 text-sm">
          <input type="checkbox" v-model="formCopilotReview" class="rounded border-gray-300" />
          Request Copilot review on PRs
        </label>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Review Task Profile</label>
          <select v-model="formReviewProfileId" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" data-testid="github-review-profile">
            <option value="">None</option>
            <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
          <p class="text-xs text-gray-500 mt-1">Creates a review task on completion using this profile</p>
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
