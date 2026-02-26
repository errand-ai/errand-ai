import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useTaskStore } from '../tasks'
import type { TaskData } from '../../composables/useApi'

// Mock useApi to prevent real fetch calls
vi.mock('../../composables/useApi', async () => {
  const actual = await vi.importActual<typeof import('../../composables/useApi')>('../../composables/useApi')
  return {
    ...actual,
    fetchTasks: vi.fn().mockResolvedValue([]),
    createTask: vi.fn().mockResolvedValue({}),
    updateTask: vi.fn().mockResolvedValue({}),
    deleteTask: vi.fn().mockResolvedValue(undefined),
  }
})

// Mock useWebSocket to avoid real connections
vi.mock('../../composables/useWebSocket', () => ({
  useWebSocket: () => ({
    status: { value: 'disconnected' },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

function makeTask(overrides: Partial<TaskData> = {}): TaskData {
  return {
    id: '1',
    title: 'Task',
    description: null,
    status: 'review',
    position: 1,
    category: 'immediate',
    execute_at: null,
    repeat_interval: null,
    repeat_until: null,
    output: null,
    runner_logs: null,
    questions: null,
    retry_count: 0,
    profile_id: null,
    profile_name: null,
    tags: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('tasksByStatus sorting', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('sorts non-scheduled columns by position ascending', () => {
    const store = useTaskStore()
    store.tasks = [
      makeTask({ id: '1', status: 'review', position: 3, created_at: '2024-01-01T00:00:00Z' }),
      makeTask({ id: '2', status: 'review', position: 1, created_at: '2024-01-02T00:00:00Z' }),
      makeTask({ id: '3', status: 'review', position: 2, created_at: '2024-01-03T00:00:00Z' }),
    ]

    const result = store.tasksByStatus('review')
    expect(result.map((t) => t.id)).toEqual(['2', '3', '1'])
  })

  it('uses created_at as tie-breaker when positions are equal', () => {
    const store = useTaskStore()
    store.tasks = [
      makeTask({ id: '1', status: 'pending', position: 1, created_at: '2024-01-03T00:00:00Z' }),
      makeTask({ id: '2', status: 'pending', position: 1, created_at: '2024-01-01T00:00:00Z' }),
      makeTask({ id: '3', status: 'pending', position: 1, created_at: '2024-01-02T00:00:00Z' }),
    ]

    const result = store.tasksByStatus('pending')
    expect(result.map((t) => t.id)).toEqual(['2', '3', '1'])
  })

  it('sorts scheduled column by execute_at ascending', () => {
    const store = useTaskStore()
    store.tasks = [
      makeTask({ id: '1', status: 'scheduled', position: 1, execute_at: '2024-02-01T00:00:00Z' }),
      makeTask({ id: '2', status: 'scheduled', position: 2, execute_at: '2024-01-01T00:00:00Z' }),
      makeTask({ id: '3', status: 'scheduled', position: 3, execute_at: '2024-01-15T00:00:00Z' }),
    ]

    const result = store.tasksByStatus('scheduled')
    expect(result.map((t) => t.id)).toEqual(['2', '3', '1'])
  })

  it('sorts scheduled column with nulls last', () => {
    const store = useTaskStore()
    store.tasks = [
      makeTask({ id: '1', status: 'scheduled', execute_at: null }),
      makeTask({ id: '2', status: 'scheduled', execute_at: '2024-01-01T00:00:00Z' }),
      makeTask({ id: '3', status: 'scheduled', execute_at: null }),
    ]

    const result = store.tasksByStatus('scheduled')
    expect(result.map((t) => t.id)).toEqual(['2', '1', '3'])
  })

  it('scheduled column ignores position, uses execute_at only', () => {
    const store = useTaskStore()
    store.tasks = [
      makeTask({ id: '1', status: 'scheduled', position: 1, execute_at: '2024-02-01T00:00:00Z' }),
      makeTask({ id: '2', status: 'scheduled', position: 3, execute_at: '2024-01-01T00:00:00Z' }),
    ]

    const result = store.tasksByStatus('scheduled')
    // position 3 comes first because its execute_at is earlier
    expect(result.map((t) => t.id)).toEqual(['2', '1'])
  })

  it('sorts completed tasks by updated_at descending (most recent first)', () => {
    const store = useTaskStore()
    store.tasks = [
      makeTask({ id: '1', status: 'completed', position: 1, updated_at: '2024-01-01T10:00:00Z' }),
      makeTask({ id: '2', status: 'completed', position: 2, updated_at: '2024-01-01T14:00:00Z' }),
      makeTask({ id: '3', status: 'completed', position: 3, updated_at: '2024-01-01T09:00:00Z' }),
    ]

    const result = store.tasksByStatus('completed')
    // Most recently completed (14:00) first, then 10:00, then 09:00
    expect(result.map((t) => t.id)).toEqual(['2', '1', '3'])
  })

  it('returns empty array for status with no tasks', () => {
    const store = useTaskStore()
    store.tasks = [
      makeTask({ id: '1', status: 'review' }),
    ]

    expect(store.tasksByStatus('completed')).toEqual([])
  })
})
