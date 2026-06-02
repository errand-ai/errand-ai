import { useAuthStore } from '../stores/auth'

export type TaskStatus = 'scheduled' | 'pending' | 'running' | 'review' | 'completed'

export interface TaskData {
  id: string
  title: string
  description: string | null
  status: TaskStatus
  position: number
  category: string | null
  execute_at: string | null
  repeat_interval: string | null
  repeat_until: string | null
  output: string | null
  runner_logs: string | null
  questions: string[] | null
  retry_count: number
  profile_id: string | null
  profile_name: string | null
  tags: string[]
  created_at: string
  updated_at: string
}

export interface TaskProfile {
  id: string
  name: string
  description: string | null
  match_rules: string | null
  model: ModelSetting | null
  system_prompt: string | null
  max_turns: number | null
  reasoning_effort: string | null
  llm_timeout: number | null
  mcp_servers: string[] | null
  litellm_mcp_servers: string[] | null
  skill_ids: string[] | null
  include_git_skills: boolean
  enabled_plugins?: string[] | null
  created_at: string
  updated_at: string
}

export interface TagData {
  id: string
  name: string
}

const BASE = '/api'

async function tryRefresh(): Promise<boolean> {
  const auth = useAuthStore()
  if (!auth.refreshToken) return false

  try {
    const resp = await fetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: auth.refreshToken }),
    })

    if (!resp.ok) return false

    const data = await resp.json()
    auth.setToken(data.access_token, data.id_token, data.refresh_token)
    return true
  } catch {
    return false
  }
}

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const auth = useAuthStore()
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }

  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }

  const res = await fetch(url, { ...options, headers })

  if (res.status === 401) {
    // Attempt token refresh and retry once
    if (await tryRefresh()) {
      const retryHeaders: Record<string, string> = {
        ...(options.headers as Record<string, string> || {}),
        'Authorization': `Bearer ${auth.token}`,
      }
      return fetch(url, { ...options, headers: retryHeaders })
    }

    auth.clearToken()
    auth.redirectToLogin()
    throw new Error('Unauthorized')
  }

  if (res.status === 403) {
    auth.setAccessDenied()
    throw new Error('Access denied')
  }

  return res
}

export async function fetchTasks(): Promise<TaskData[]> {
  const res = await authFetch(`${BASE}/tasks`)
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.status}`)
  return res.json()
}

export async function createTask(input: string): Promise<TaskData> {
  const res = await authFetch(`${BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input }),
  })
  if (!res.ok) throw new Error(`Failed to create task: ${res.status}`)
  return res.json()
}

export async function updateTask(id: string, data: { title?: string; description?: string; status?: TaskStatus; position?: number; tags?: string[]; category?: string; execute_at?: string; repeat_interval?: string; repeat_until?: string; profile_id?: string | null }): Promise<TaskData> {
  const res = await authFetch(`${BASE}/tasks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to update task: ${res.status}`)
  return res.json()
}

export async function deleteTask(id: string): Promise<void> {
  const res = await authFetch(`${BASE}/tasks/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Failed to delete task: ${res.status}`)
}

export async function fetchArchivedTasks(): Promise<TaskData[]> {
  const res = await authFetch(`${BASE}/tasks/archived`)
  if (!res.ok) throw new Error(`Failed to fetch archived tasks: ${res.status}`)
  return res.json()
}

export async function fetchTags(query: string): Promise<TagData[]> {
  const res = await authFetch(`${BASE}/tags?q=${encodeURIComponent(query)}`)
  if (!res.ok) throw new Error(`Failed to fetch tags: ${res.status}`)
  return res.json()
}

// --- LLM Provider API ---

export interface LlmProviderData {
  id: string
  name: string
  base_url: string
  api_key: string  // masked
  provider_type: string
  is_default: boolean
  source: string
  created_at: string | null
  updated_at: string | null
}

export interface ModelSetting {
  provider_id: string | null
  model: string
}

export async function fetchProviders(): Promise<LlmProviderData[]> {
  const res = await authFetch(`${BASE}/llm/providers`)
  if (!res.ok) throw new Error(`Failed to fetch providers: ${res.status}`)
  return res.json()
}

export async function createProvider(data: { name: string; base_url: string; api_key: string }): Promise<LlmProviderData> {
  const res = await authFetch(`${BASE}/llm/providers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to create provider: ${res.status}`)
  }
  return res.json()
}

export async function updateProvider(id: string, data: { name?: string; base_url?: string; api_key?: string }): Promise<LlmProviderData> {
  const res = await authFetch(`${BASE}/llm/providers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to update provider: ${res.status}`)
  }
  return res.json()
}

export async function deleteProvider(id: string): Promise<void> {
  const res = await authFetch(`${BASE}/llm/providers/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to delete provider: ${res.status}`)
  }
}

export async function setDefaultProvider(id: string): Promise<LlmProviderData> {
  const res = await authFetch(`${BASE}/llm/providers/${id}/default`, { method: 'PUT' })
  if (!res.ok) throw new Error(`Failed to set default provider: ${res.status}`)
  return res.json()
}

export interface ModelInfo {
  id: string
  supports_reasoning: boolean | null
  max_output_tokens: number | null
}

export async function fetchProviderModels(id: string, mode?: string): Promise<ModelInfo[]> {
  const url = mode
    ? `${BASE}/llm/providers/${id}/models?mode=${encodeURIComponent(mode)}`
    : `${BASE}/llm/providers/${id}/models`
  const res = await authFetch(url)
  if (!res.ok) throw new Error(`Failed to fetch models: ${res.status}`)
  return res.json()
}

// --- LLM Model Settings ---

export async function saveLlmModel(setting: ModelSetting): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ llm_model: setting }),
  })
  if (!res.ok) throw new Error(`Failed to save model: ${res.status}`)
  return res.json()
}

export async function saveTitleGenerationTimeout(timeout: number): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title_generation_timeout: timeout }),
  })
  if (!res.ok) throw new Error(`Failed to save title-generation timeout: ${res.status}`)
  return res.json()
}

export async function saveTaskProcessingTimeout(timeout: number): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_processing_timeout: timeout }),
  })
  if (!res.ok) throw new Error(`Failed to save task-processing timeout: ${res.status}`)
  return res.json()
}

export async function saveTranscriptionTimeout(timeout: number): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcription_timeout: timeout }),
  })
  if (!res.ok) throw new Error(`Failed to save transcription timeout: ${res.status}`)
  return res.json()
}

export interface LlmModelsAndTimeouts {
  llm_model: ModelSetting
  task_processing_model: ModelSetting
  transcription_model: ModelSetting | null
  title_generation_timeout: number
  task_processing_timeout: number
  transcription_timeout: number
}

export async function saveLlmModelsAndTimeouts(payload: LlmModelsAndTimeouts): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Failed to save model settings: ${res.status}`)
  return res.json()
}

export async function saveTaskProcessingModel(setting: ModelSetting): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_processing_model: setting }),
  })
  if (!res.ok) throw new Error(`Failed to save task processing model: ${res.status}`)
  return res.json()
}

export async function fetchTranscriptionStatus(): Promise<{ enabled: boolean }> {
  const res = await authFetch(`${BASE}/transcribe/status`)
  if (!res.ok) return { enabled: false }
  return res.json()
}

export async function transcribeAudio(blob: Blob): Promise<string> {
  const formData = new FormData()
  formData.append('file', blob, 'recording.webm')
  const res = await authFetch(`${BASE}/transcribe`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) throw new Error(`Transcription failed: ${res.status}`)
  const data = await res.json()
  return data.text
}

export async function saveTranscriptionModel(setting: ModelSetting | null): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcription_model: setting }),
  })
  if (!res.ok) throw new Error(`Failed to save transcription model: ${res.status}`)
  return res.json()
}

export interface PlatformCredentialField {
  key: string
  label: string
  type: string
  required: boolean
  options?: { value: string; label: string }[]
  auth_mode?: string
  help_text?: string
  default?: string
  editable?: boolean
}

export interface PlatformInfo {
  id: string
  label: string
  capabilities: string[]
  credential_schema: PlatformCredentialField[]
  status: string
  last_verified_at: string | null
  field_values?: Record<string, string>
}

export async function fetchPlatforms(): Promise<PlatformInfo[]> {
  const res = await authFetch(`${BASE}/platforms`)
  if (!res.ok) throw new Error(`Failed to fetch platforms: ${res.status}`)
  return res.json()
}

export async function savePlatformCredentials(platformId: string, credentials: Record<string, string>): Promise<{ status: string }> {
  const res = await authFetch(`${BASE}/platforms/${platformId}/credentials`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials),
  })
  if (!res.ok) throw new Error(`Failed to save credentials: ${res.status}`)
  return res.json()
}

export async function deletePlatformCredentials(platformId: string): Promise<void> {
  const res = await authFetch(`${BASE}/platforms/${platformId}/credentials`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Failed to delete credentials: ${res.status}`)
}

export async function fetchPlatformCredentialStatus(platformId: string): Promise<{ platform_id: string; status: string; last_verified_at: string | null; configured_fields: string[]; field_values: Record<string, string> }> {
  const res = await authFetch(`${BASE}/platforms/${platformId}/credentials`)
  if (!res.ok) throw new Error(`Failed to fetch credential status: ${res.status}`)
  return res.json()
}

export async function patchPlatformCredentials(platformId: string, fields: Record<string, string>): Promise<{ status: string; last_verified_at: string | null }> {
  const res = await authFetch(`${BASE}/platforms/${platformId}/credentials`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  if (!res.ok) throw new Error(`Failed to update credentials: ${res.status}`)
  return res.json()
}

export async function verifyPlatformCredentials(platformId: string): Promise<{ status: string; last_verified_at: string | null }> {
  const res = await authFetch(`${BASE}/platforms/${platformId}/credentials/verify`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to verify credentials: ${res.status}`)
  return res.json()
}

export interface CloudStorageProviderStatus {
  available: boolean
  connected: boolean
  mode: 'direct' | 'cloud' | null
  /** Only present for providers that gate on an MCP URL (currently OneDrive).
   *  Google Workspace uses the bundled `gws` CLI and omits this field. */
  mcp_configured?: boolean
  user_email?: string
  user_name?: string
  /** True when stored OAuth scopes are narrower than the currently required set
   *  (Google Workspace only — OneDrive does not include this field). */
  reauth_required?: boolean
  /** OAuth scopes actually granted on the most recent authorization. The
   *  Google Workspace section uses this for per-badge active-state rendering
   *  (a partial grant should leave non-granted badges muted). */
  granted_scopes?: string[]
}

export interface CloudStorageStatus {
  google_drive: CloudStorageProviderStatus
  onedrive: CloudStorageProviderStatus
}

export async function fetchCloudStorageStatus(): Promise<CloudStorageStatus> {
  const res = await authFetch(`${BASE}/integrations/status`)
  if (!res.ok) throw new Error(`Failed to fetch integration status: ${res.status}`)
  return res.json()
}

export async function authorizeCloudStorage(provider: string): Promise<{ redirect_url: string }> {
  const res = await authFetch(`${BASE}/integrations/${provider}/authorize`)
  if (!res.ok) throw new Error(`Failed to start authorization: ${res.status}`)
  return res.json()
}

export async function disconnectCloudStorage(provider: string): Promise<void> {
  const res = await authFetch(`${BASE}/integrations/${provider}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to disconnect ${provider}: ${res.status}`)
}

export interface LitellmMcpServer {
  alias: string
  server_name?: string
  description?: string
  tools: string[]
}

export interface LitellmMcpResponse {
  available: boolean
  servers: Record<string, LitellmMcpServer>
  enabled: string[]
}

export async function fetchLitellmMcpServers(): Promise<LitellmMcpResponse> {
  const res = await authFetch(`${BASE}/litellm/mcp-servers`)
  if (!res.ok) throw new Error(`Failed to fetch LiteLLM MCP servers: ${res.status}`)
  return res.json()
}

export async function fetchTaskProfiles(): Promise<TaskProfile[]> {
  const res = await authFetch(`${BASE}/task-profiles`)
  if (!res.ok) throw new Error(`Failed to fetch task profiles: ${res.status}`)
  return res.json()
}

export async function createTaskProfile(data: Record<string, unknown>): Promise<TaskProfile> {
  const res = await authFetch(`${BASE}/task-profiles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to create profile: ${res.status}`)
  }
  return res.json()
}

export async function updateTaskProfile(id: string, data: Record<string, unknown>): Promise<TaskProfile> {
  const res = await authFetch(`${BASE}/task-profiles/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to update profile: ${res.status}`)
  }
  return res.json()
}

export async function deleteTaskProfile(id: string): Promise<void> {
  const res = await authFetch(`${BASE}/task-profiles/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to delete profile: ${res.status}`)
}

// --- Task Generators ---

export interface TaskGeneratorData {
  id: string
  type: string
  enabled: boolean
  profile_id: string | null
  config: Record<string, any> | null
  created_at: string
  updated_at: string
}

export async function fetchEmailGenerator(): Promise<TaskGeneratorData | null> {
  const res = await authFetch(`${BASE}/task-generators/email`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`Failed to fetch email generator: ${res.status}`)
  return res.json()
}

export async function upsertEmailGenerator(data: {
  enabled: boolean
  profile_id: string | null
  config: Record<string, any>
}): Promise<TaskGeneratorData> {
  const res = await authFetch(`${BASE}/task-generators/email`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to save email generator: ${res.status}`)
  return res.json()
}

// --- Webhook Triggers ---

export interface WebhookTrigger {
  id: string
  name: string
  source: string
  enabled: boolean
  profile_id: string | null
  filters: Record<string, any>
  actions: Record<string, any>
  task_prompt: string | null
  has_secret: boolean
  cloud_webhook_url: string | null
  created_at: string | null
  updated_at: string | null
}

export async function fetchWebhookTriggers(): Promise<WebhookTrigger[]> {
  const res = await authFetch(`${BASE}/webhook-triggers`)
  if (!res.ok) throw new Error(`Failed to fetch webhook triggers: ${res.status}`)
  return res.json()
}

export async function fetchWebhookTrigger(id: string): Promise<WebhookTrigger> {
  const res = await authFetch(`${BASE}/webhook-triggers/${id}`)
  if (!res.ok) throw new Error(`Failed to fetch webhook trigger: ${res.status}`)
  return res.json()
}

export async function createWebhookTrigger(data: {
  name: string
  source: string
  enabled?: boolean
  profile_id?: string | null
  filters?: Record<string, unknown>
  actions?: Record<string, unknown>
  task_prompt?: string | null
}): Promise<WebhookTrigger> {
  const res = await authFetch(`${BASE}/webhook-triggers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to create webhook trigger: ${res.status}`)
  }
  return res.json()
}

export async function updateWebhookTrigger(id: string, data: Partial<{
  name: string
  source: string
  enabled: boolean
  profile_id: string | null
  filters: Record<string, unknown>
  actions: Record<string, unknown>
  task_prompt: string | null
}>): Promise<WebhookTrigger> {
  const res = await authFetch(`${BASE}/webhook-triggers/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to update webhook trigger: ${res.status}`)
  }
  return res.json()
}

export async function deleteWebhookTrigger(id: string): Promise<void> {
  const res = await authFetch(`${BASE}/webhook-triggers/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to delete webhook trigger: ${res.status}`)
}

// --- GitHub Credentials ---

export async function fetchGithubCredentialStatus(): Promise<{ status: string }> {
  const platforms = await fetchPlatforms()
  const github = platforms.find((p: any) => p.id === 'github')
  return { status: github?.status || 'disconnected' }
}

export async function introspectGithubProject(org: string, projectNumber: number): Promise<{
  project_node_id: string
  title: string
  status_field: { field_id: string; options: Array<{id: string; name: string}> } | null
}> {
  const res = await authFetch(`${BASE}/webhook-triggers/github/introspect-project`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ org, project_number: projectNumber }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to introspect project: ${res.status}`)
  }
  return res.json()
}

// --- Jira Credentials ---

export interface JiraCredentialStatus {
  platform_id: string
  status: string
  site_url: string | null
  last_verified_at: string | null
  display_name?: string
}

export async function fetchJiraCredentialStatus(): Promise<JiraCredentialStatus> {
  const res = await authFetch(`${BASE}/credentials/jira`)
  if (!res.ok) throw new Error(`Failed to fetch Jira credential status: ${res.status}`)
  return res.json()
}

export async function saveJiraCredentials(data: {
  cloud_id: string
  api_token: string
  site_url: string
  service_account_email: string
}): Promise<JiraCredentialStatus> {
  const res = await authFetch(`${BASE}/credentials/jira`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Failed to save Jira credentials: ${res.status}`)
  }
  return res.json()
}

export async function deleteJiraCredentials(): Promise<void> {
  const res = await authFetch(`${BASE}/credentials/jira`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to delete Jira credentials: ${res.status}`)
}

// --- Plugin Marketplaces ---

export type MarketplaceSourceType = 'github' | 'git' | 'http' | 'local'

export interface Marketplace {
  id: string
  name: string
  source_type: MarketplaceSourceType
  source_url: string
  ref: string | null
  has_auth_token: boolean
  enabled: boolean
  predefined: boolean
  last_synced_at: string | null
  last_sync_status: 'ok' | 'error' | null
  last_sync_error: string | null
  plugin_count: number
  created_at: string | null
  updated_at: string | null
}

export interface MarketplacePluginEntry {
  name: string
  source: unknown
  version?: string
  description?: string
  displayName?: string
  keywords?: string[]
  category?: string
  unsupported?: boolean
  available_versions?: string[]
  skills?: string[]
  mcp_servers?: string[]
}

export interface MarketplaceCreateInput {
  name: string
  source_type: MarketplaceSourceType
  source_url: string
  ref?: string | null
  auth_token?: string | null
}

export interface MarketplacePatchInput {
  enabled?: boolean
  name?: string
  source_url?: string
  ref?: string | null
  auth_token?: string | null
}

export async function fetchMarketplaces(): Promise<Marketplace[]> {
  const res = await authFetch(`${BASE}/marketplaces`)
  if (!res.ok) throw new Error(`Failed to fetch marketplaces: ${res.status}`)
  return res.json()
}

export async function createMarketplace(data: MarketplaceCreateInput): Promise<Marketplace> {
  const res = await authFetch(`${BASE}/marketplaces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to add marketplace: ${res.status}`)
  }
  return res.json()
}

export async function patchMarketplace(id: string, data: MarketplacePatchInput): Promise<Marketplace> {
  const res = await authFetch(`${BASE}/marketplaces/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to update marketplace: ${res.status}`)
  }
  return res.json()
}

export async function deleteMarketplace(id: string): Promise<void> {
  const res = await authFetch(`${BASE}/marketplaces/${id}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to remove marketplace: ${res.status}`)
  }
}

export async function resyncMarketplace(id: string): Promise<void> {
  const res = await authFetch(`${BASE}/marketplaces/${id}/resync`, { method: 'POST' })
  if (!res.ok && res.status !== 202) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to resync marketplace: ${res.status}`)
  }
}

export async function fetchMarketplacePlugins(id: string): Promise<MarketplacePluginEntry[]> {
  const res = await authFetch(`${BASE}/marketplaces/${id}/plugins`)
  if (!res.ok) throw new Error(`Failed to fetch marketplace plugins: ${res.status}`)
  return res.json()
}

// --- Plugins ---

export interface PluginMcpServer {
  raw: string
  namespaced: string
}

export interface PluginIgnoredArtifact {
  type: string
  count: number
}

export interface PluginSkillConflict {
  skill: string
  other: string
}

export interface Plugin {
  id: string
  plugin_name: string
  marketplace_id: string | null
  marketplace_name?: string | null
  installed_version: string
  latest_available_version: string | null
  enabled: boolean
  manifest: Record<string, unknown> | null
  ignored_artifacts: PluginIgnoredArtifact[] | null
  skill_conflicts: PluginSkillConflict[] | null
  update_available: boolean
  skills: string[]
  mcp_servers: PluginMcpServer[]
  installed_at: string | null
  last_checked_at: string | null
}

export interface PluginMarketplaceInstallInput {
  marketplace_id: string
  plugin_name: string
  version?: string
}

export interface PluginManualInstallInput {
  source_type: 'github' | 'git'
  source_url: string
  ref?: string | null
  auth_token?: string | null
}

export async function fetchPlugins(): Promise<Plugin[]> {
  const res = await authFetch(`${BASE}/plugins`)
  if (!res.ok) throw new Error(`Failed to fetch plugins: ${res.status}`)
  return res.json()
}

export async function installPlugin(
  data: PluginMarketplaceInstallInput | PluginManualInstallInput,
): Promise<Plugin> {
  const res = await authFetch(`${BASE}/plugins`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to install plugin: ${res.status}`)
  }
  return res.json()
}

export async function patchPlugin(id: string, data: { enabled?: boolean }): Promise<Plugin> {
  const res = await authFetch(`${BASE}/plugins/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to update plugin: ${res.status}`)
  }
  return res.json()
}

export async function deletePlugin(id: string): Promise<void> {
  const res = await authFetch(`${BASE}/plugins/${id}`, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to remove plugin: ${res.status}`)
  }
}

export async function updatePlugin(id: string): Promise<Plugin> {
  const res = await authFetch(`${BASE}/plugins/${id}/update`, { method: 'POST' })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Failed to update plugin: ${res.status}`)
  }
  return res.json()
}

