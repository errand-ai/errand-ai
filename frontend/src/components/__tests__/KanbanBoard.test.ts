import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import KanbanBoard from '../KanbanBoard.vue'
import { useTaskStore } from '../../stores/tasks'
import type { TaskData } from '../../composables/useApi'

// Mock the useApi composable to prevent real fetch calls
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

const COLUMN_LABELS = ['Review', 'Scheduled', 'Pending', 'Running', 'Completed']

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
    retry_count: 0,
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
  // Set tasks before mount so the initial render sees them
  store.tasks = tasks
  const wrapper = mount(KanbanBoard, { global: { plugins: [pinia] } })
  return { wrapper, store }
}

describe('KanbanBoard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders 5 columns with correct labels when tasks exist', () => {
    const { wrapper } = mountWithTasks(makeTasks([{ title: 'Test', status: 'review' }]))
    const headings = wrapper.findAll('h2')
    const labels = headings.map((h) => h.text().replace(/\d+/, '').trim())
    expect(labels).toEqual(COLUMN_LABELS)
  })

  it('places tasks in correct columns', () => {
    const { wrapper } = mountWithTasks(makeTasks([
      { title: 'Alpha', status: 'review' },
      { title: 'Beta', status: 'running' },
      { title: 'Gamma', status: 'completed' },
    ]))

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    // Review column (index 0) should contain Alpha
    expect(columns[0].text()).toContain('Alpha')
    // Running column (index 3) should contain Beta
    expect(columns[3].text()).toContain('Beta')
    // Completed column (index 4) should contain Gamma
    expect(columns[4].text()).toContain('Gamma')
  })

  it('shows board-level empty state when no tasks exist', () => {
    const { wrapper } = mountWithTasks([])

    const emptyState = wrapper.find('[data-testid="board-empty-state"]')
    expect(emptyState.exists()).toBe(true)
    expect(emptyState.text()).toContain('No tasks yet')
  })

  it('shows pill badge with count in column headers', () => {
    const { wrapper } = mountWithTasks(makeTasks([
      { title: 'Alpha', status: 'review' },
      { title: 'Beta', status: 'review' },
    ]))

    const badges = wrapper.findAll('[data-testid="column-count"]')
    expect(badges.length).toBe(5)
    // Review column should show 2
    expect(badges[0].text()).toBe('2')
  })

  it('calls store.updateTask on drop to different column', async () => {
    const { wrapper, store } = mountWithTasks(
      makeTasks([{ id: '42', title: 'Drag me', status: 'review' }])
    )
    store.updateTask = vi.fn().mockResolvedValue(undefined)

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    // Simulate drop on "Scheduled" column (index 1)
    const dropEvent = new Event('drop', { bubbles: true }) as any
    dropEvent.dataTransfer = { getData: () => '42' }
    dropEvent.preventDefault = vi.fn()
    columns[1].element.dispatchEvent(dropEvent)
    await nextTick()

    expect(store.updateTask).toHaveBeenCalledWith('42', { status: 'scheduled' })
  })

  it('does not call store.updateTask on same-column drop in non-reorderable column', async () => {
    const { wrapper, store } = mountWithTasks(
      makeTasks([{ id: '42', title: 'Stay here', status: 'completed' }])
    )
    store.updateTask = vi.fn()

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    // Drop on "Completed" column (index 4) — same as current status, non-reorderable
    const dropEvent = new Event('drop', { bubbles: true }) as any
    dropEvent.dataTransfer = { getData: () => '42' }
    dropEvent.preventDefault = vi.fn()
    columns[4].element.dispatchEvent(dropEvent)
    await nextTick()

    expect(store.updateTask).not.toHaveBeenCalled()
  })

  it('highlights column on drag enter', async () => {
    const { wrapper } = mountWithTasks(makeTasks([{ title: 'Test', status: 'review' }]))

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    await columns[1].trigger('dragenter')
    await nextTick()

    // After dragenter, the column should have the highlight ring class
    expect(columns[1].classes()).toContain('ring-2')
    expect(columns[1].classes()).toContain('ring-blue-400')
  })

  // --- Delete confirmation modal ---

  it('shows delete confirmation dialog when delete is triggered on a card', async () => {
    const { wrapper } = mountWithTasks(
      makeTasks([{ id: '10', title: 'Delete me' }])
    )

    // Click the delete button on the TaskCard
    const deleteBtn = wrapper.find('button[title="Delete task"]')
    await deleteBtn.trigger('click')
    await nextTick()

    // The delete dialog should contain the task title
    const dialog = wrapper.find('dialog')
    expect(dialog.exists()).toBe(true)
    expect(dialog.text()).toContain('Delete this task?')
    expect(dialog.text()).toContain('Delete me')
  })

  it('calls store.removeTask when delete is confirmed', async () => {
    const { wrapper, store } = mountWithTasks(
      makeTasks([{ id: '10', title: 'Delete me' }])
    )
    store.removeTask = vi.fn().mockResolvedValue(undefined)

    // Open the delete modal
    const deleteBtn = wrapper.find('button[title="Delete task"]')
    await deleteBtn.trigger('click')
    await nextTick()

    // Click the confirm "Delete" button in the dialog
    const dialog = wrapper.find('dialog')
    const confirmBtn = dialog.findAll('button').find((b) => b.text() === 'Delete')!
    await confirmBtn.trigger('click')
    await nextTick()

    expect(store.removeTask).toHaveBeenCalledWith('10')
  })

  it('does not call store.removeTask when delete is cancelled', async () => {
    const { wrapper, store } = mountWithTasks(
      makeTasks([{ id: '10', title: 'Keep me' }])
    )
    store.removeTask = vi.fn()

    // Open the delete modal
    const deleteBtn = wrapper.find('button[title="Delete task"]')
    await deleteBtn.trigger('click')
    await nextTick()

    // Click Cancel in the dialog
    const dialog = wrapper.find('dialog')
    const cancelBtn = dialog.findAll('button').find((b) => b.text() === 'Cancel')!
    await cancelBtn.trigger('click')
    await nextTick()

    expect(store.removeTask).not.toHaveBeenCalled()
  })

  // --- Intra-column reorder ---

  it('calls store.updateTask with position on same-column drop in reorderable column', async () => {
    const { wrapper, store } = mountWithTasks(
      makeTasks([
        { id: '1', title: 'First', status: 'review', position: 1 },
        { id: '2', title: 'Second', status: 'review', position: 2 },
      ])
    )
    store.updateTask = vi.fn().mockResolvedValue(undefined)

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    // Drop task '1' (position 1) on the Review column (same status, reorderable)
    // In jsdom getBoundingClientRect returns zeros, so insertIndex = cards.length = 2
    // targetPosition = lastTask.position + 1 = 3, which differs from task.position = 1
    const dropEvent = new Event('drop', { bubbles: true }) as any
    dropEvent.dataTransfer = { getData: () => '1' }
    dropEvent.preventDefault = vi.fn()
    dropEvent.clientY = 9999 // below all cards
    columns[0].element.dispatchEvent(dropEvent)
    await nextTick()

    expect(store.updateTask).toHaveBeenCalledWith('1', { position: 3 })
  })
})
