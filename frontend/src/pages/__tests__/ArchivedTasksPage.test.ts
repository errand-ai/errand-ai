import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import ArchivedTasksPage from '../ArchivedTasksPage.vue'

const { mockTasks } = vi.hoisted(() => {
  const mockTasks = [
    {
      id: '1',
      title: 'Archived task',
      description: 'Old task',
      status: 'archived',
      position: 0,
      category: 'immediate',
      execute_at: null,
      repeat_interval: null,
      repeat_until: null,
      output: null,
      runner_logs: null,
      retry_count: 0,
      tags: ['tag1'],
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-15T00:00:00Z',
    },
    {
      id: '2',
      title: 'Deleted task',
      description: null,
      status: 'deleted',
      position: 0,
      category: 'immediate',
      execute_at: null,
      repeat_interval: null,
      repeat_until: null,
      output: 'Task execution output here',
      runner_logs: null,
      retry_count: 0,
      tags: [],
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-10T00:00:00Z',
    },
  ]
  return { mockTasks }
})

vi.mock('../../composables/useApi', async () => {
  const actual = await vi.importActual<typeof import('../../composables/useApi')>('../../composables/useApi')
  return {
    ...actual,
    fetchArchivedTasks: vi.fn().mockResolvedValue(mockTasks),
    fetchTags: vi.fn().mockResolvedValue([]),
  }
})

describe('ArchivedTasksPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders heading', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()
    expect(wrapper.text()).toContain('Archived Tasks')
  })

  it('displays tasks in a table', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Archived task')
    expect(wrapper.text()).toContain('Deleted task')
  })

  it('shows status badges', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    expect(wrapper.text()).toContain('archived')
    expect(wrapper.text()).toContain('deleted')
  })

  it('shows tags as pills', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    expect(wrapper.text()).toContain('tag1')
  })

  it('shows View Output button only for tasks with output', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    // First task has no output
    expect(rows[0].find('button').exists()).toBe(false)
    // Second task has output
    const btn = rows[1].findAll('button').find(b => b.text() === 'View Output')
    expect(btn).toBeDefined()
  })

  it('clicking View Output opens output modal', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    const btn = rows[1].findAll('button').find(b => b.text() === 'View Output')!
    await btn.trigger('click')
    await flushPromises()

    const outputModal = wrapper.findComponent({ name: 'TaskOutputModal' })
    expect(outputModal.exists()).toBe(true)
    expect(outputModal.props('title')).toBe('Deleted task')
    expect(outputModal.props('output')).toBe('Task execution output here')

    // Edit modal should NOT have opened
    const editModal = wrapper.findComponent({ name: 'TaskEditModal' })
    expect(editModal.exists()).toBe(false)
  })

  it('opens read-only modal on row click', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(2)

    await rows[0].trigger('click')
    await flushPromises()

    // TaskEditModal should be rendered with read-only
    const modal = wrapper.findComponent({ name: 'TaskEditModal' })
    expect(modal.exists()).toBe(true)
    expect(modal.props('readOnly')).toBe(true)
  })

  // --- Search, filter, sort tests ---

  it('renders search input and status filter', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    expect(wrapper.find('[data-testid="search-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="status-filter"]').exists()).toBe(true)
  })

  it('filters tasks by search query', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    const searchInput = wrapper.find('[data-testid="search-input"]')
    await searchInput.setValue('Archived')
    await nextTick()

    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('Archived task')
  })

  it('filters tasks by status', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    const select = wrapper.find('[data-testid="status-filter"]')
    await select.setValue('deleted')
    await nextTick()

    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('Deleted task')
  })

  it('shows result count', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    const count = wrapper.find('[data-testid="result-count"]')
    expect(count.text()).toBe('2 tasks')
  })

  it('sorts by title when header is clicked', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    await wrapper.find('[data-testid="sort-title"]').trigger('click')
    await nextTick()

    const rows = wrapper.findAll('tbody tr')
    expect(rows[0].text()).toContain('Archived task')
    expect(rows[1].text()).toContain('Deleted task')
  })

  it('shows skeleton loading state', () => {
    const wrapper = mount(ArchivedTasksPage)
    // Before flushPromises, loading should be true
    const skeleton = wrapper.find('[data-testid="skeleton-loading"]')
    expect(skeleton.exists()).toBe(true)
  })
})

describe('ArchivedTasksPage — empty state', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    // Override mock to return empty array for this suite
    const { fetchArchivedTasks } = vi.mocked(
      await import('../../composables/useApi')
    )
    fetchArchivedTasks.mockResolvedValueOnce([])
  })

  it('shows empty state when no tasks exist', async () => {
    const wrapper = mount(ArchivedTasksPage)
    await flushPromises()

    const emptyState = wrapper.find('[data-testid="archive-empty-state"]')
    expect(emptyState.exists()).toBe(true)
    expect(emptyState.text()).toContain('No archived tasks yet')
  })
})
