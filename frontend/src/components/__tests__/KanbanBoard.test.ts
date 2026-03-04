import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
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
    emits: ['task-update', 'task-edit', 'task-delete', 'view-output', 'view-live-logs', 'view-static-logs'],
  },
  TaskForm: {
    name: 'TaskForm',
    template: '<div data-testid="task-form"><slot name="voice" :onTranscription="() => {}" /></div>',
    emits: ['task-created'],
  },
  TaskEditModal: {
    name: 'TaskEditModal',
    template: '<div data-testid="edit-modal" />',
    props: ['task', 'readOnly'],
    emits: ['save', 'cancel', 'delete'],
  },
  TaskOutputModal: {
    name: 'TaskOutputModal',
    template: '<div data-testid="output-modal" />',
    props: ['title', 'output'],
    emits: ['close'],
  },
  TaskLogViewer: {
    name: 'TaskLogViewer',
    template: '<div data-testid="log-viewer" />',
    props: ['mode', 'taskId', 'logData', 'streamUrl'],
    emits: ['close', 'finished'],
  },
  DeleteConfirmModal: {
    name: 'DeleteConfirmModal',
    template: '<div data-testid="delete-modal" />',
    props: ['title'],
    emits: ['confirm', 'cancel'],
  },
  AudioRecorder: {
    name: 'AudioRecorder',
    template: '<div data-testid="audio-recorder" />',
    emits: ['transcription'],
  },
}))

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

function mountWithTasks(tasks: TaskData[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useTaskStore()
  store.tasks = tasks

  const auth = useAuthStore()
  auth.setToken(fakeJwt({
    sub: 'editor-1',
    resource_access: { 'errand': { roles: ['editor'] } },
  }))

  const wrapper = mount(KanbanBoard, { global: { plugins: [pinia] } })
  return { wrapper, store }
}

describe('KanbanBoard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('[]', { status: 200 })))
  })

  it('shows board-level empty state when no tasks exist', () => {
    const { wrapper } = mountWithTasks([])
    const emptyState = wrapper.find('[data-testid="board-empty-state"]')
    expect(emptyState.exists()).toBe(true)
    expect(emptyState.text()).toContain('No tasks yet')
  })

  it('renders TaskBoard when tasks exist', () => {
    const { wrapper } = mountWithTasks(makeTasks([{ title: 'Test' }]))
    const board = wrapper.findComponent({ name: 'TaskBoard' })
    expect(board.exists()).toBe(true)
  })

  it('passes tasks to TaskBoard', () => {
    const tasks = makeTasks([{ title: 'Alpha' }, { title: 'Beta' }])
    const { wrapper } = mountWithTasks(tasks)
    const board = wrapper.findComponent({ name: 'TaskBoard' })
    expect(board.props('tasks')).toEqual(tasks)
  })

  it('calls store.updateTask on task-update event', async () => {
    const { wrapper, store } = mountWithTasks(makeTasks([{ id: '42', title: 'Drag me' }]))
    store.updateTask = vi.fn().mockResolvedValue(undefined)

    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('task-update', { id: '42', status: 'scheduled' })
    await nextTick()

    expect(store.updateTask).toHaveBeenCalledWith('42', { id: '42', status: 'scheduled' })
  })

  it('opens edit modal on task-edit event', async () => {
    const task = makeTasks([{ id: '10', title: 'Edit me' }])[0]
    const { wrapper } = mountWithTasks([task])

    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('task-edit', task)
    await nextTick()

    const editModal = wrapper.findComponent({ name: 'TaskEditModal' })
    expect(editModal.exists()).toBe(true)
    expect(editModal.props('task')).toMatchObject({ id: '10', title: 'Edit me' })
  })

  // --- Delete confirmation ---

  it('opens delete confirmation on task-delete event', async () => {
    const task = makeTasks([{ id: '10', title: 'Delete me' }])[0]
    const { wrapper } = mountWithTasks([task])

    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('task-delete', task)
    await nextTick()

    const deleteModal = wrapper.findComponent({ name: 'DeleteConfirmModal' })
    expect(deleteModal.exists()).toBe(true)
    expect(deleteModal.props('title')).toBe('Delete me')
  })

  it('calls store.removeTask when delete is confirmed', async () => {
    const task = makeTasks([{ id: '10', title: 'Delete me' }])[0]
    const { wrapper, store } = mountWithTasks([task])
    store.removeTask = vi.fn().mockResolvedValue(undefined)

    // Open delete modal
    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('task-delete', task)
    await nextTick()

    // Confirm deletion
    const deleteModal = wrapper.findComponent({ name: 'DeleteConfirmModal' })
    deleteModal.vm.$emit('confirm')
    await flushPromises()

    expect(store.removeTask).toHaveBeenCalledWith('10')
  })

  it('does not call store.removeTask when delete is cancelled', async () => {
    const task = makeTasks([{ id: '10', title: 'Keep me' }])[0]
    const { wrapper, store } = mountWithTasks([task])
    store.removeTask = vi.fn()

    // Open delete modal
    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('task-delete', task)
    await nextTick()

    // Cancel deletion
    const deleteModal = wrapper.findComponent({ name: 'DeleteConfirmModal' })
    deleteModal.vm.$emit('cancel')
    await nextTick()

    expect(store.removeTask).not.toHaveBeenCalled()
  })

  // --- Log viewer ---

  it('opens TaskLogViewer in live mode for running tasks', async () => {
    const task = makeTasks([{ id: '5', title: 'Running task', status: 'running' }])[0]
    const { wrapper } = mountWithTasks([task])

    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('view-live-logs', task)
    await nextTick()

    const logViewer = wrapper.findComponent({ name: 'TaskLogViewer' })
    expect(logViewer.exists()).toBe(true)
    expect(logViewer.props('mode')).toBe('live')
    expect(logViewer.props('taskId')).toBe('5')
  })

  it('opens TaskLogViewer in static mode for completed tasks', async () => {
    const task = makeTasks([{ id: '6', title: 'Done task', status: 'completed', runner_logs: '{"type":"agent_start"}' }])[0]
    const { wrapper } = mountWithTasks([task])

    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('view-static-logs', task)
    await nextTick()

    const logViewer = wrapper.findComponent({ name: 'TaskLogViewer' })
    expect(logViewer.exists()).toBe(true)
    expect(logViewer.props('mode')).toBe('static')
    expect(logViewer.props('logData')).toBe('{"type":"agent_start"}')
  })

  // --- Output modal ---

  it('opens output modal on view-output event', async () => {
    const task = makeTasks([{ id: '7', title: 'Has output', output: 'Result text' }])[0]
    const { wrapper } = mountWithTasks([task])

    const board = wrapper.findComponent({ name: 'TaskBoard' })
    board.vm.$emit('view-output', task)
    await nextTick()

    const outputModal = wrapper.findComponent({ name: 'TaskOutputModal' })
    expect(outputModal.exists()).toBe(true)
    expect(outputModal.props('title')).toBe('Has output')
    expect(outputModal.props('output')).toBe('Result text')
  })
})
