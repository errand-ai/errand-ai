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
  questions: null,
  retry_count: 0,
  profile_id: null,
  profile_name: null,
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
    const timeEl = wrapper.find('[data-testid="execute-at-time"]')
    expect(timeEl.exists()).toBe(true)
    expect(timeEl.text()).toBeTruthy()
  })

  it('shows execute_at on non-scheduled columns when execute_at is set', () => {
    const taskWithExecuteAt: TaskData = {
      ...task,
      execute_at: new Date(Date.now() + 3600000).toISOString(),
    }
    const wrapper = mount(TaskCard, {
      props: { task: taskWithExecuteAt, columnStatus: 'pending' },
    })
    const timeEl = wrapper.find('[data-testid="execute-at-time"]')
    expect(timeEl.exists()).toBe(true)
  })

  it('hides execute_at when execute_at is null', () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'scheduled' },
    })
    const timeEl = wrapper.find('[data-testid="execute-at-time"]')
    expect(timeEl.exists()).toBe(false)
  })

  // --- Description preview ---

  it('shows description preview when description is set', () => {
    const taskWithDesc: TaskData = { ...task, description: 'Some long description text here' }
    const wrapper = mount(TaskCard, { props: { task: taskWithDesc } })
    const preview = wrapper.find('[data-testid="description-preview"]')
    expect(preview.exists()).toBe(true)
    expect(preview.text()).toContain('Some long description text here')
  })

  it('hides description preview when description is null', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    const preview = wrapper.find('[data-testid="description-preview"]')
    expect(preview.exists()).toBe(false)
  })

  // --- Repeating indicator ---

  it('shows repeating indicator for repeating tasks', () => {
    const repeatingTask: TaskData = {
      ...task,
      category: 'repeating',
      repeat_interval: '1d',
    }
    const wrapper = mount(TaskCard, { props: { task: repeatingTask } })
    const indicator = wrapper.find('[data-testid="repeating-indicator"]')
    expect(indicator.exists()).toBe(true)
    expect(indicator.text()).toContain('1d')
  })

  it('hides repeating indicator for non-repeating tasks', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    const indicator = wrapper.find('[data-testid="repeating-indicator"]')
    expect(indicator.exists()).toBe(false)
  })

  // --- Running indicator ---

  it('shows running indicator when columnStatus is running', () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'running' },
    })
    const indicator = wrapper.find('[data-testid="running-indicator"]')
    expect(indicator.exists()).toBe(true)
    expect(indicator.text()).toContain('Running...')
  })

  it('applies border accent when running', () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'running' },
    })
    const card = wrapper.find('.border-l-2.border-blue-400')
    expect(card.exists()).toBe(true)
  })

  it('hides running indicator when not running', () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'pending' },
    })
    const indicator = wrapper.find('[data-testid="running-indicator"]')
    expect(indicator.exists()).toBe(false)
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

  // --- Log button ---

  it('shows log button when columnStatus is running', () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'running' },
    })
    const btn = wrapper.find('button[title="View logs"]')
    expect(btn.exists()).toBe(true)
  })

  it('hides log button when columnStatus is not running and no runner_logs', () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'pending' },
    })
    const btn = wrapper.find('button[title="View logs"]')
    expect(btn.exists()).toBe(false)
  })

  it('shows log button when columnStatus is completed and task has runner_logs', () => {
    const completedWithLogs: TaskData = { ...task, status: 'completed', runner_logs: 'some log data' }
    const wrapper = mount(TaskCard, {
      props: { task: completedWithLogs, columnStatus: 'completed' },
    })
    const btn = wrapper.find('button[title="View logs"]')
    expect(btn.exists()).toBe(true)
  })

  it('shows log button when columnStatus is review and task has runner_logs', () => {
    const reviewWithLogs: TaskData = { ...task, status: 'review', runner_logs: 'some log data' }
    const wrapper = mount(TaskCard, {
      props: { task: reviewWithLogs, columnStatus: 'review' },
    })
    const btn = wrapper.find('button[title="View logs"]')
    expect(btn.exists()).toBe(true)
  })

  it('hides log button when columnStatus is completed and no runner_logs', () => {
    const completedNoLogs: TaskData = { ...task, status: 'completed', runner_logs: null }
    const wrapper = mount(TaskCard, {
      props: { task: completedNoLogs, columnStatus: 'completed' },
    })
    const btn = wrapper.find('button[title="View logs"]')
    expect(btn.exists()).toBe(false)
  })

  it('emits view-logs event when log button is clicked', async () => {
    const wrapper = mount(TaskCard, {
      props: { task, columnStatus: 'running' },
    })
    await wrapper.find('button[title="View logs"]').trigger('click')
    expect(wrapper.emitted('view-logs')).toHaveLength(1)
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

  // --- Profile badge ---

  it('shows profile badge when profile_name is set', () => {
    const taskWithProfile: TaskData = { ...task, profile_id: 'abc-123', profile_name: 'email-triage' }
    const wrapper = mount(TaskCard, { props: { task: taskWithProfile } })
    const badge = wrapper.find('[data-testid="profile-badge"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toContain('email-triage')
  })

  it('hides profile badge when profile_name is null', () => {
    const wrapper = mount(TaskCard, { props: { task } })
    const badge = wrapper.find('[data-testid="profile-badge"]')
    expect(badge.exists()).toBe(false)
  })
})
