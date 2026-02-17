import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import type { TaskData } from '../../composables/useApi'

const mockNow = ref(new Date('2025-06-15T12:00:00Z'))

vi.mock('../../composables/useNow', () => ({
  useNow: () => mockNow,
}))

import TaskCard from '../TaskCard.vue'

const baseTask: TaskData = {
  id: '1',
  title: 'Countdown test',
  description: null,
  status: 'scheduled',
  position: 1,
  category: 'scheduled',
  execute_at: '2025-06-15T12:30:00Z',
  repeat_interval: null,
  repeat_until: null,
  output: null,
  runner_logs: null,
  questions: null,
  retry_count: 0,
  tags: [],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('TaskCard countdown refresh', () => {
  it('updates relative time display when the now ref changes', async () => {
    mockNow.value = new Date('2025-06-15T12:00:00Z')

    const wrapper = mount(TaskCard, {
      props: { task: baseTask, columnStatus: 'scheduled' },
    })

    const timeEl = wrapper.find('.text-blue-600')
    expect(timeEl.exists()).toBe(true)
    expect(timeEl.text()).toBe('in 30m')

    // Advance mock now by 25 minutes
    mockNow.value = new Date('2025-06-15T12:25:00Z')
    await nextTick()

    expect(wrapper.find('.text-blue-600').text()).toBe('in 5m')
  })

  it('does not run timer for non-scheduled cards', () => {
    const pendingTask: TaskData = { ...baseTask, status: 'pending', execute_at: null }
    const wrapper = mount(TaskCard, {
      props: { task: pendingTask, columnStatus: 'pending' },
    })
    const timeEl = wrapper.find('.text-blue-600')
    expect(timeEl.exists()).toBe(false)
  })
})
