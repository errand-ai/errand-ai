import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import KanbanBoard from '../KanbanBoard.vue'
import { useTaskStore } from '../../stores/tasks'
import { useAuthStore } from '../../stores/auth'
import type { TaskData } from '../../composables/useApi'

vi.mock('../../composables/useWebSocket', () => ({
  useWebSocket: () => ({
    status: ref('disconnected'),
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
let originalFetch: typeof globalThis.fetch

beforeAll(() => {
  originalFetch = globalThis.fetch
  vi.stubGlobal('fetch', fetchMock)
})

afterAll(() => {
  vi.stubGlobal('fetch', originalFetch)
})

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

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-signature`
}

function makeTasks(overrides: Partial<TaskData>[] = []): TaskData[] {
  return overrides.map((o, i) => ({
    id: String(i + 1),
    title: `Task ${i + 1}`,
    description: null,
    status: 'new' as const,
    position: i + 1,
    category: 'immediate',
    execute_at: null,
    repeat_interval: null,
    repeat_until: null,
    output: null,
    runner_logs: null,
    retry_count: 0,
    tags: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...o,
  }))
}

function mountAsViewer(tasks: TaskData[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const taskStore = useTaskStore()
  taskStore.tasks = tasks

  const auth = useAuthStore()
  auth.setToken(fakeJwt({
    sub: 'viewer-1',
    resource_access: { 'content-manager': { roles: ['viewer'] } },
  }))

  const wrapper = mount(KanbanBoard, { global: { plugins: [pinia] } })
  return { wrapper, taskStore, auth }
}

function mountAsEditor(tasks: TaskData[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const taskStore = useTaskStore()
  taskStore.tasks = tasks

  const auth = useAuthStore()
  auth.setToken(fakeJwt({
    sub: 'editor-1',
    resource_access: { 'content-manager': { roles: ['editor'] } },
  }))

  const wrapper = mount(KanbanBoard, { global: { plugins: [pinia] } })
  return { wrapper, taskStore, auth }
}

describe('KanbanBoard RBAC — viewer restrictions', () => {
  it('viewer does not see the task creation form', () => {
    const { wrapper } = mountAsViewer(makeTasks([{ title: 'A task' }]))
    // TaskForm should not be rendered
    const form = wrapper.findComponent({ name: 'TaskForm' })
    expect(form.exists()).toBe(false)
  })

  it('viewer does not see delete buttons on task cards', () => {
    const { wrapper } = mountAsViewer(makeTasks([{ title: 'A task' }]))
    const deleteBtn = wrapper.find('button[title="Delete task"]')
    expect(deleteBtn.exists()).toBe(false)
  })

  it('viewer task cards are not draggable', () => {
    const { wrapper } = mountAsViewer(makeTasks([{ title: 'A task' }]))
    const card = wrapper.find('[class*="rounded-lg bg-white"]')
    expect(card.attributes('draggable')).toBe('false')
  })

  it('editor sees the task creation form', () => {
    const { wrapper } = mountAsEditor(makeTasks([{ title: 'A task' }]))
    const form = wrapper.findComponent({ name: 'TaskForm' })
    expect(form.exists()).toBe(true)
  })

  it('editor sees delete buttons on non-running task cards', () => {
    const { wrapper } = mountAsEditor(makeTasks([{ title: 'A task', status: 'new' }]))
    const deleteBtn = wrapper.find('button[title="Delete task"]')
    expect(deleteBtn.exists()).toBe(true)
  })

  it('running column hides delete button for all users', () => {
    const { wrapper } = mountAsEditor(makeTasks([{ title: 'Running task', status: 'running' }]))
    const deleteBtn = wrapper.find('button[title="Delete task"]')
    expect(deleteBtn.exists()).toBe(false)
  })
})
