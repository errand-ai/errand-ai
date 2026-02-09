import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskCard from '../TaskCard.vue'
import type { TaskData } from '../../composables/useApi'

const task: TaskData = {
  id: '1',
  title: 'Process report',
  status: 'running',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
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
})
