import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskEditModal from '../TaskEditModal.vue'
import type { TaskData } from '../../composables/useApi'

// Mock fetchTags used by the tag autocomplete
vi.mock('../../composables/useApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../composables/useApi')>()
  return {
    ...actual,
    fetchTags: vi.fn().mockResolvedValue([]),
  }
})

const task: TaskData = {
  id: '1',
  title: 'Process report',
  description: 'A longer description of the task',
  status: 'running',
  tags: ['urgent'],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

const taskNoDescription: TaskData = {
  ...task,
  description: null,
  tags: [],
}

describe('TaskEditModal', () => {
  it('shows current task data in fields', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const titleInput = wrapper.find('#edit-title').element as HTMLInputElement
    const statusSelect = wrapper.find('#edit-status').element as HTMLSelectElement

    expect(titleInput.value).toBe('Process report')
    expect(statusSelect.value).toBe('running')
  })

  it('status selector shows 6 valid statuses (no need-input)', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const options = wrapper.findAll('#edit-status option')
    expect(options).toHaveLength(6)

    const labels = options.map((o) => o.text())
    expect(labels).toEqual([
      'New', 'Scheduled', 'Pending', 'Running', 'Review', 'Completed',
    ])
  })

  it('emits save event with updated data including description and tags', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('#edit-title').setValue('Updated report')
    await wrapper.find('form').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect(emitted).toHaveLength(1)
    expect(emitted![0][0]).toEqual({
      title: 'Updated report',
      description: 'A longer description of the task',
      status: 'running',
      tags: ['urgent'],
    })
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
    // Find the Cancel button (not the tag remove buttons)
    const cancelBtn = wrapper.findAll('button[type="button"]').find((b) => b.text() === 'Cancel')!
    await cancelBtn.trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(1)
    expect(wrapper.emitted('save')).toBeUndefined()
  })

  // --- Description field ---

  it('shows description textarea with existing value', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const textarea = wrapper.find('#edit-description').element as HTMLTextAreaElement
    expect(textarea.value).toBe('A longer description of the task')
  })

  it('shows empty description textarea when description is null', () => {
    const wrapper = mount(TaskEditModal, { props: { task: taskNoDescription } })
    const textarea = wrapper.find('#edit-description').element as HTMLTextAreaElement
    expect(textarea.value).toBe('')
  })

  it('includes updated description in save payload', async () => {
    const wrapper = mount(TaskEditModal, { props: { task: taskNoDescription } })
    await wrapper.find('#edit-description').setValue('New description')
    await wrapper.find('form').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect(emitted![0][0]).toMatchObject({ description: 'New description' })
  })

  // --- Tags ---

  it('displays existing tags as removable pills', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    expect(wrapper.text()).toContain('urgent')
    const removeButtons = wrapper.findAll('.inline-flex button')
    expect(removeButtons).toHaveLength(1)
  })

  it('removes a tag when remove button is clicked', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('.inline-flex button').trigger('click')

    // Tag should be removed from the pills
    expect(wrapper.text()).not.toContain('urgent')
  })

  it('adds a tag when typing and pressing Enter in tag input', async () => {
    const wrapper = mount(TaskEditModal, { props: { task: taskNoDescription } })
    const tagInput = wrapper.find('input[placeholder="Add tag..."]')

    await tagInput.setValue('new-tag')
    await tagInput.trigger('keydown', { key: 'Enter' })

    expect(wrapper.text()).toContain('new-tag')
  })

  it('includes tags in save payload', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('form').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect(emitted![0][0]).toMatchObject({ tags: ['urgent'] })
  })
})
