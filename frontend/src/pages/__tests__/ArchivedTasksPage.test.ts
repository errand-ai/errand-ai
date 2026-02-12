import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ArchivedTasksPage from '../ArchivedTasksPage.vue'

vi.mock('../../composables/useApi', async () => {
  const actual = await vi.importActual<typeof import('../../composables/useApi')>('../../composables/useApi')
  return {
    ...actual,
    fetchArchivedTasks: vi.fn().mockResolvedValue([
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
        output: null,
        runner_logs: null,
        retry_count: 0,
        tags: [],
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-10T00:00:00Z',
      },
    ]),
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
})
