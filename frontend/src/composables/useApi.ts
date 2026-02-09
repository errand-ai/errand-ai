import { useAuthStore } from '../stores/auth'

export type TaskStatus = 'new' | 'scheduled' | 'pending' | 'running' | 'review' | 'completed'

export interface TaskData {
  id: string
  title: string
  description: string | null
  status: TaskStatus
  tags: string[]
  created_at: string
  updated_at: string
}

export interface TagData {
  id: string
  name: string
}

const BASE = '/api'

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

export async function updateTask(id: string, data: { title?: string; description?: string; status?: TaskStatus; tags?: string[] }): Promise<TaskData> {
  const res = await authFetch(`${BASE}/tasks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to update task: ${res.status}`)
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
