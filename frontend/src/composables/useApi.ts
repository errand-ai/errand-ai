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
  tags: string[]
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
    window.location.href = '/auth/login'
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

export async function updateTask(id: string, data: { title?: string; description?: string; status?: TaskStatus; position?: number; tags?: string[]; category?: string; execute_at?: string; repeat_interval?: string; repeat_until?: string }): Promise<TaskData> {
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

export async function fetchLlmModels(): Promise<string[]> {
  const res = await authFetch(`${BASE}/llm/models`)
  if (!res.ok) throw new Error(`Failed to fetch models: ${res.status}`)
  return res.json()
}

export async function saveLlmModel(model: string): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ llm_model: model }),
  })
  if (!res.ok) throw new Error(`Failed to save model: ${res.status}`)
  return res.json()
}

export async function saveTaskProcessingModel(model: string): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_processing_model: model }),
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

export async function fetchTranscriptionModels(): Promise<string[]> {
  const res = await authFetch(`${BASE}/llm/transcription-models`)
  if (!res.ok) throw new Error(`Failed to fetch transcription models: ${res.status}`)
  return res.json()
}

export async function saveTranscriptionModel(model: string | null): Promise<Record<string, unknown>> {
  const res = await authFetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcription_model: model }),
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
}

export interface PlatformInfo {
  id: string
  label: string
  capabilities: string[]
  credential_schema: PlatformCredentialField[]
  status: string
  last_verified_at: string | null
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

export async function verifyPlatformCredentials(platformId: string): Promise<{ status: string; last_verified_at: string | null }> {
  const res = await authFetch(`${BASE}/platforms/${platformId}/credentials/verify`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to verify credentials: ${res.status}`)
  return res.json()
}
