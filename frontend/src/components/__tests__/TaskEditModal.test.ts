import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskEditModal from '../TaskEditModal.vue'
import type { TaskData } from '../../composables/useApi'

const task: TaskData = {
  id: '1',
  title: 'Process report',
  status: 'running',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('TaskEditModal', () => {
  it('shows current task data in fields', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const titleInput = wrapper.find('#edit-title').element as HTMLInputElement
    const statusSelect = wrapper.find('#edit-status').element as HTMLSelectElement

    expect(titleInput.value).toBe('Process report')
    expect(statusSelect.value).toBe('running')
  })

  it('status selector shows all 7 valid statuses', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const options = wrapper.findAll('#edit-status option')
    expect(options).toHaveLength(7)

    const labels = options.map((o) => o.text())
    expect(labels).toEqual([
      'New', 'Need Input', 'Scheduled', 'Pending', 'Running', 'Review', 'Completed',
    ])
  })

  it('emits save event with updated data on save', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('#edit-title').setValue('Updated report')
    await wrapper.find('form').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect(emitted).toHaveLength(1)
    expect(emitted![0][0]).toEqual({ title: 'Updated report', status: 'running' })
  })

  it('shows validation error when title is empty on save', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('#edit-title').setValue('')
    await wrapper.find('form').trigger('submit')

    expect(wrapper.text()).toContain('Title cannot be empty')
    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('emits cancel event on cancel button click', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('button[type="button"]').trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(1)
    expect(wrapper.emitted('save')).toBeUndefined()
  })
})
