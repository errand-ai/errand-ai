import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskCard from '../TaskCard.vue'
import type { TaskData } from '../../composables/useApi'

const task: TaskData = {
  id: '1',
  title: 'Process report',
  description: null,
  status: 'running',
  position: 1,
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
}

const taskWithTags: TaskData = {
  ...task,
  tags: ['urgent', 'backend'],
}

const scheduledTask: TaskData = {
  ...task,
  status: 'scheduled',
  category: 'scheduled',
  execute_at: new Date(Date.now() + 3600000).toISOString(), // 1 hour from now
}

describe('TaskCard', () => {
  it('renders the task title', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    expect(wrapper.text()).toContain('Process report')
  })

  it('renders an edit button', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    const button = wrapper.find('button[title="Edit task"]')
    expect(button.exists()).toBe(true)
  })

  it('has draggable="true" attribute', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    const card = wrapper.find('[draggable="true"]')
    expect(card.exists()).toBe(true)
  })

  it('emits edit event when edit button is clicked', async () => {
    const wrapper = mount(TaskCard, { props: { task } })
    await wrapper.find('button[title="Edit task"]').trigger('click')
    expect(wrapper.emitted('edit')).toHaveLength(1)
  })

  it('does not show status text', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    // Status should not be displayed (it's implied by the column)
    expect(wrapper.text()).not.toContain('running')
  })

  it('displays tags as pills when present', () => {
    const wrapper = mount(TaskCard, { props: { task: taskWithTags } })
    expect(wrapper.text()).toContain('urgent')
    expect(wrapper.text()).toContain('backend')
    const pills = wrapper.findAll('span.inline-block')
    expect(pills).toHaveLength(2)
  })

  it('does not render tag section when tags are empty', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    const pills = wrapper.findAll('span.inline-block')
    expect(pills).toHaveLength(0)
  })

  // --- execute_at display ---

  it('shows execute_at as relative time when columnStatus is scheduled', () => {
    const wrapper = mount(TaskCard, {
      props: { task: scheduledTask, columnStatus: 'scheduled' },
    })
    // The relative time text should be rendered (e.g. "in 1h")
    const timeEl = wrapper.find('.text-blue-600')
    expect(timeEl.exists()).toBe(true)
    expect(timeEl.text()).toBeTruthy()
  })

  it('hides execute_at when columnStatus is not scheduled', () => {
    const wrapper = mount(TaskCard, {
      props: { task: scheduledTask, columnStatus: 'pending' },
    })
    const timeEl = wrapper.find('.text-blue-600')
    expect(timeEl.exists()).toBe(false)
  })

  it('hides execute_at when execute_at is null even in scheduled column', () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'scheduled' },
    })
    const timeEl = wrapper.find('.text-blue-600')
    expect(timeEl.exists()).toBe(false)
  })

  // --- Output button ---

  it('shows output button when columnStatus is review and task has output', () => {
    const reviewTask: TaskData = { ...task, status: 'review', output: 'some output' }
    const wrapper = mount(TaskCard, { props: { task: reviewTask, columnStatus: 'review' } })
    const btn = wrapper.find('button[title="View output"]')
    expect(btn.exists()).toBe(true)
  })

  it('shows output button when columnStatus is completed and task has output', () => {
    const completedTask: TaskData = { ...task, status: 'completed', output: 'result data' }
    const wrapper = mount(TaskCard, { props: { task: completedTask, columnStatus: 'completed' } })
    const btn = wrapper.find('button[title="View output"]')
    expect(btn.exists()).toBe(true)
  })

  it('shows output button when columnStatus is scheduled and task has output', () => {
    const failedScheduled: TaskData = { ...scheduledTask, output: 'error log' }
    const wrapper = mount(TaskCard, { props: { task: failedScheduled, columnStatus: 'scheduled' } })
    const btn = wrapper.find('button[title="View output"]')
    expect(btn.exists()).toBe(true)
  })

  it('hides output button when task output is null', () => {
    const reviewTask: TaskData = { ...task, status: 'review', output: null }
    const wrapper = mount(TaskCard, { props: { task: reviewTask, columnStatus: 'review' } })
    const btn = wrapper.find('button[title="View output"]')
    expect(btn.exists()).toBe(false)
  })

  it('hides output button in non-output columns even with output', () => {
    const runningTask: TaskData = { ...task, status: 'running', output: 'some output' }
    const wrapper = mount(TaskCard, { props: { task: runningTask, columnStatus: 'running' } })
    const btn = wrapper.find('button[title="View output"]')
    expect(btn.exists()).toBe(false)
  })

  it('emits view-output event when output button is clicked', async () => {
    const reviewTask: TaskData = { ...task, status: 'review', output: 'output text' }
    const wrapper = mount(TaskCard, { props: { task: reviewTask, columnStatus: 'review' } })
    await wrapper.find('button[title="View output"]').trigger('click')
    expect(wrapper.emitted('view-output')).toHaveLength(1)
  })

  // --- Delete button ---

  it('renders a delete button', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    const button = wrapper.find('button[title="Delete task"]')
    expect(button.exists()).toBe(true)
  })

  it('emits delete event when delete button is clicked', async () => {
    const wrapper = mount(TaskCard, { props: { task } })
    await wrapper.find('button[title="Delete task"]').trigger('click')
    expect(wrapper.emitted('delete')).toHaveLength(1)
  })
})
