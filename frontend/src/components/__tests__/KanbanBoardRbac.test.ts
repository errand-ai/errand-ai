import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import KanbanBoard from '../KanbanBoard.vue'
import { useTaskStore } from '../../stores/tasks'
import { useAuthStore } from '../../stores/auth'
import type { TaskData } from '../../composables/useApi'

// Mock shared library components
vi.mock('@errand-ai/ui-components', () => ({
  TaskBoard: {
    name: 'TaskBoard',
    template: '<div data-testid="task-board" />',
    props: ['tasks', 'userRole', 'loading'],
  },
  TaskForm: {
    name: 'TaskForm',
    template: '<div data-testid="task-form"><slot name="voice" :onTranscription="() => {}" /></div>',
  },
  TaskEditModal: { name: 'TaskEditModal', template: '<div />', props: ['task', 'readOnly'] },
  TaskOutputModal: { name: 'TaskOutputModal', template: '<div />', props: ['title', 'output'] },
  TaskLogViewer: { name: 'TaskLogViewer', template: '<div />', props: ['mode', 'taskId', 'logData', 'streamUrl'] },
  DeleteConfirmModal: { name: 'DeleteConfirmModal', template: '<div />', props: ['title'] },
  AudioRecorder: { name: 'AudioRecorder', template: '<div />' },
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
    status: 'review' as const,
    position: i + 1,
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
    ...o,
  }))
}

function mountAsRole(role: string, tasks: TaskData[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const taskStore = useTaskStore()
  taskStore.tasks = tasks

  const auth = useAuthStore()
  auth.setToken(fakeJwt({
    sub: `${role}-1`,
    resource_access: { 'errand': { roles: [role] } },
  }))

  const wrapper = mount(KanbanBoard, { global: { plugins: [pinia] } })
  return { wrapper, taskStore, auth }
}

describe('KanbanBoard RBAC — viewer restrictions', () => {
  it('viewer does not see the task creation form', () => {
    const { wrapper } = mountAsRole('viewer', makeTasks([{ title: 'A task' }]))
    const form = wrapper.findComponent({ name: 'TaskForm' })
    expect(form.exists()).toBe(false)
  })

  it('viewer passes "viewer" role to TaskBoard', () => {
    const { wrapper } = mountAsRole('viewer', makeTasks([{ title: 'A task' }]))
    const board = wrapper.findComponent({ name: 'TaskBoard' })
    expect(board.props('userRole')).toBe('viewer')
  })

  it('editor sees the task creation form', () => {
    const { wrapper } = mountAsRole('editor', makeTasks([{ title: 'A task' }]))
    const form = wrapper.findComponent({ name: 'TaskForm' })
    expect(form.exists()).toBe(true)
  })

  it('editor passes "editor" role to TaskBoard', () => {
    const { wrapper } = mountAsRole('editor', makeTasks([{ title: 'A task' }]))
    const board = wrapper.findComponent({ name: 'TaskBoard' })
    expect(board.props('userRole')).toBe('editor')
  })

  it('admin passes "admin" role to TaskBoard', () => {
    const { wrapper } = mountAsRole('admin', makeTasks([{ title: 'A task' }]))
    const board = wrapper.findComponent({ name: 'TaskBoard' })
    expect(board.props('userRole')).toBe('admin')
  })

  it('admin sees the task creation form', () => {
    const { wrapper } = mountAsRole('admin', makeTasks([{ title: 'A task' }]))
    const form = wrapper.findComponent({ name: 'TaskForm' })
    expect(form.exists()).toBe(true)
  })
})
