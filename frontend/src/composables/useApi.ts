import { useAuthStore } from '../stores/auth'

export type TaskStatus = 'new' | 'need-input' | 'scheduled' | 'pending' | 'running' | 'review' | 'completed'

export interface TaskData {
  id: string
  title: string
  status: TaskStatus
  created_at: string
  updated_at: string
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

export async function createTask(title: string): Promise<TaskData> {
  const res = await authFetch(`${BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!res.ok) throw new Error(`Failed to create task: ${res.status}`)
  return res.json()
}

export async function updateTask(id: string, data: { title?: string; status?: TaskStatus }): Promise<TaskData> {
  const res = await authFetch(`${BASE}/tasks/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to update task: ${res.status}`)
  return res.json()
}
