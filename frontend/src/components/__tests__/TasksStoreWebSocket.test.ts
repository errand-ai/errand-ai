import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'
import type { WebSocketStatus, UseWebSocketReturn, UseWebSocketOptions } from '../../composables/useWebSocket'

// Capture the onMessage callback so we can invoke it from tests
let capturedOptions: UseWebSocketOptions | null = null
const mockStatus = ref<WebSocketStatus>('disconnected')
const mockConnect = vi.fn()
const mockDisconnect = vi.fn()

vi.mock('../../composables/useWebSocket', () => ({
  useWebSocket: (options: UseWebSocketOptions): UseWebSocketReturn => {
    capturedOptions = options
    return {
      status: mockStatus,
      connect: mockConnect,
      disconnect: mockDisconnect,
    }
  },
}))

// Mock useApi to prevent actual fetch calls
vi.mock('../../composables/useApi', () => ({
  fetchTasks: vi.fn().mockResolvedValue([]),
  createTask: vi.fn().mockResolvedValue({ id: 'new-1', title: 'New', description: null, status: 'review', position: 0, category: 'immediate', execute_at: null, repeat_interval: null, repeat_until: null, tags: [], created_at: '', updated_at: '', output: null, runner_logs: null, questions: null, retry_count: 0 }),
  updateTask: vi.fn().mockResolvedValue({ id: '1', title: 'Test', description: null, status: 'running', position: 0, category: 'immediate', execute_at: null, repeat_interval: null, repeat_until: null, tags: [], created_at: '', updated_at: '', output: null, runner_logs: null, questions: null, retry_count: 0 }),
  deleteTask: vi.fn().mockResolvedValue(undefined),
}))

import { useTaskStore } from '../../stores/tasks'

describe('TaskStore WebSocket integration', () => {
  beforeEach(() => {
    capturedOptions = null
    mockStatus.value = 'disconnected'
    mockConnect.mockClear()
    mockDisconnect.mockClear()
    setActivePinia(createPinia())
  })

  it('adds a new task on task_created event', () => {
    const store = useTaskStore()

    // The store constructor calls useWebSocket, which captures the options
    expect(capturedOptions).not.toBeNull()

    capturedOptions!.onMessage({
      event: 'task_created',
      task: { id: 'ws-1', title: 'WebSocket task', description: null, status: 'review', position: 0, category: 'immediate', execute_at: null, repeat_interval: null, repeat_until: null, tags: [], output: null, runner_logs: null, questions: null, retry_count: 0, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
    })

    expect(store.tasks).toHaveLength(1)
    expect(store.tasks[0].id).toBe('ws-1')
    expect(store.tasks[0].title).toBe('WebSocket task')
  })

  it('updates an existing task on task_updated event', () => {
    const store = useTaskStore()
    store.tasks = [
      { id: 'existing-1', title: 'Existing', description: null, status: 'review', position: 0, category: 'immediate', execute_at: null, repeat_interval: null, repeat_until: null, tags: [], output: null, runner_logs: null, questions: null, retry_count: 0, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' },
    ]

    capturedOptions!.onMessage({
      event: 'task_updated',
      task: { id: 'existing-1', title: 'Existing', description: null, status: 'running', position: 0, category: 'immediate', execute_at: null, repeat_interval: null, repeat_until: null, tags: [], created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:01' },
    })

    expect(store.tasks[0].status).toBe('running')
  })

  it('does not duplicate task on repeated task_created', () => {
    const store = useTaskStore()

    const task = { id: 'dup-1', title: 'Dup', description: null, status: 'review' as const, category: 'immediate', execute_at: null, repeat_interval: null, repeat_until: null, tags: [] as string[], output: null, runner_logs: null, questions: null, retry_count: 0, created_at: '', updated_at: '' }
    capturedOptions!.onMessage({ event: 'task_created', task })
    capturedOptions!.onMessage({ event: 'task_created', task })

    expect(store.tasks.filter((t) => t.id === 'dup-1')).toHaveLength(1)
  })

  it('calls connect on start and disconnect on stop', () => {
    const store = useTaskStore()
    store.start()
    expect(mockConnect).toHaveBeenCalled()

    store.stop()
    expect(mockDisconnect).toHaveBeenCalled()
  })

  it('starts polling when WebSocket disconnects', async () => {
    useTaskStore()
    // Simulate WebSocket connected then disconnected
    mockStatus.value = 'connected'
    await vi.dynamicImportSettled()
    mockStatus.value = 'disconnected'

    // The watcher on wsStatus should trigger startPolling
    // We can verify by checking that the store would be in polling mode
    // (fetchTasks is called on startPolling)
    const { fetchTasks } = await import('../../composables/useApi')
    // Give the watcher time to fire
    await new Promise((r) => setTimeout(r, 0))
    expect(fetchTasks).toHaveBeenCalled()
  })
})
