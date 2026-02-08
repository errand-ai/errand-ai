export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface TaskData {
  id: string
  title: string
  status: TaskStatus
  created_at: string
  updated_at: string
}

const BASE = '/api'

export async function fetchTasks(): Promise<TaskData[]> {
  const res = await fetch(`${BASE}/tasks`)
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.status}`)
  return res.json()
}

export async function createTask(title: string): Promise<TaskData> {
  const res = await fetch(`${BASE}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!res.ok) throw new Error(`Failed to create task: ${res.status}`)
  return res.json()
}
