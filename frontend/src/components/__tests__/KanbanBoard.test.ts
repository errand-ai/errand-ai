import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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
  }
})

const COLUMN_LABELS = ['New', 'Need Input', 'Scheduled', 'Pending', 'Running', 'Review', 'Completed']

function makeTasks(overrides: Partial<TaskData>[] = []): TaskData[] {
  return overrides.map((o, i) => ({
    id: String(i + 1),
    title: `Task ${i + 1}`,
    status: 'new' as const,
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

  it('renders 7 columns with correct labels', () => {
    const wrapper = mount(KanbanBoard)
    const headings = wrapper.findAll('h2')
    const labels = headings.map((h) => h.text().replace(/\(\d+\)/, '').trim())
    expect(labels).toEqual(COLUMN_LABELS)
  })

  it('places tasks in correct columns', () => {
    const { wrapper } = mountWithTasks(makeTasks([
      { title: 'Alpha', status: 'new' },
      { title: 'Beta', status: 'running' },
      { title: 'Gamma', status: 'completed' },
    ]))

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    // New column (index 0) should contain Alpha
    expect(columns[0].text()).toContain('Alpha')
    // Running column (index 4) should contain Beta
    expect(columns[4].text()).toContain('Beta')
    // Completed column (index 6) should contain Gamma
    expect(columns[6].text()).toContain('Gamma')
  })

  it('shows "No tasks" placeholder in empty columns', () => {
    const { wrapper } = mountWithTasks([])

    const placeholders = wrapper.findAll('p.italic')
    expect(placeholders.length).toBe(7)
    placeholders.forEach((p) => {
      expect(p.text()).toBe('No tasks')
    })
  })

  it('calls store.updateTask on drop to different column', async () => {
    const { wrapper, store } = mountWithTasks(
      makeTasks([{ id: '42', title: 'Drag me', status: 'new' }])
    )
    store.updateTask = vi.fn().mockResolvedValue(undefined)

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    // Simulate drop on "Scheduled" column (index 2)
    const dropEvent = new Event('drop', { bubbles: true }) as any
    dropEvent.dataTransfer = { getData: () => '42' }
    dropEvent.preventDefault = vi.fn()
    columns[2].element.dispatchEvent(dropEvent)
    await nextTick()

    expect(store.updateTask).toHaveBeenCalledWith('42', { status: 'scheduled' })
  })

  it('does not call store.updateTask on same-column drop', async () => {
    const { wrapper, store } = mountWithTasks(
      makeTasks([{ id: '42', title: 'Stay here', status: 'new' }])
    )
    store.updateTask = vi.fn()

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    // Drop on "New" column (index 0) — same as current status
    const dropEvent = new Event('drop', { bubbles: true }) as any
    dropEvent.dataTransfer = { getData: () => '42' }
    dropEvent.preventDefault = vi.fn()
    columns[0].element.dispatchEvent(dropEvent)
    await nextTick()

    expect(store.updateTask).not.toHaveBeenCalled()
  })

  it('highlights column on drag enter', async () => {
    const wrapper = mount(KanbanBoard)

    const columns = wrapper.findAll('[class*="rounded-lg p-4"]')
    await columns[2].trigger('dragenter')
    await nextTick()

    // After dragenter, the column should have the highlight ring class
    expect(columns[2].classes()).toContain('ring-2')
    expect(columns[2].classes()).toContain('ring-blue-400')
  })
})
