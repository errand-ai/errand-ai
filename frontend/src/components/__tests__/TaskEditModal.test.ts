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
  position: 1,
  category: 'immediate',
  execute_at: null,
  repeat_interval: null,
  repeat_until: null,
  output: null,
  runner_logs: null,
  questions: null,
  retry_count: 0,
  tags: ['urgent'],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

const taskNoDescription: TaskData = {
  ...task,
  description: null,
  tags: [],
}

const repeatingTask: TaskData = {
  ...task,
  category: 'repeating',
  execute_at: '2026-02-11T09:00:00Z',
  repeat_interval: '1d',
  repeat_until: '2026-03-31T00:00:00Z',
}

describe('TaskEditModal', () => {
  it('shows current task data in fields', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const titleInput = wrapper.find('#edit-title').element as HTMLInputElement
    const statusSelect = wrapper.find('#edit-status').element as HTMLSelectElement

    expect(titleInput.value).toBe('Process report')
    expect(statusSelect.value).toBe('running')
  })

  it('status selector shows 5 valid statuses (no new or need-input)', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const options = wrapper.findAll('#edit-status option')
    expect(options).toHaveLength(5)

    const labels = options.map((o) => o.text())
    expect(labels).toEqual([
      'Review', 'Scheduled', 'Pending', 'Running', 'Completed',
    ])
  })

  it('emits save event with updated data including all fields', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('#edit-title').setValue('Updated report')
    await wrapper.find('form').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect(emitted).toHaveLength(1)
    const payload = emitted![0][0] as Record<string, unknown>
    expect(payload.title).toBe('Updated report')
    expect(payload.description).toBe('A longer description of the task')
    expect(payload.status).toBe('running')
    expect(payload.tags).toEqual(['urgent'])
    expect(payload.category).toBe('immediate')
    // execute_at should be undefined since it's null/empty
    expect(payload.execute_at).toBeUndefined()
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
    // Find the Cancel button (not the tag remove buttons or delete button)
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

  // --- Category dropdown ---

  it('shows category dropdown with 3 options', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const options = wrapper.findAll('#edit-category option')
    expect(options).toHaveLength(3)
    expect(options.map((o) => o.text())).toEqual(['Immediate', 'Scheduled', 'Repeating'])
  })

  it('category dropdown reflects task category', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const select = wrapper.find('#edit-category').element as HTMLSelectElement
    expect(select.value).toBe('immediate')
  })

  it('includes selected category in save payload', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('#edit-category').setValue('scheduled')
    await wrapper.find('form').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect((emitted![0][0] as Record<string, unknown>).category).toBe('scheduled')
  })

  // --- Execute at datetime input ---

  it('shows execute_at datetime-local input', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const input = wrapper.find('#edit-execute-at')
    expect(input.exists()).toBe(true)
    expect(input.attributes('type')).toBe('datetime-local')
  })

  it('execute_at input is empty when task has no execute_at', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const input = wrapper.find('#edit-execute-at').element as HTMLInputElement
    expect(input.value).toBe('')
  })

  // --- Repeat fields conditional visibility ---

  it('hides repeat_interval and repeat_until when category is not repeating', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    expect(wrapper.find('#edit-repeat-interval').exists()).toBe(false)
    expect(wrapper.find('#edit-repeat-until').exists()).toBe(false)
  })

  it('shows repeat_interval and repeat_until when category is repeating', () => {
    const wrapper = mount(TaskEditModal, { props: { task: repeatingTask } })
    expect(wrapper.find('#edit-repeat-interval').exists()).toBe(true)
    expect(wrapper.find('#edit-repeat-until').exists()).toBe(true)
  })

  it('shows repeat fields after changing category to repeating', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    // Initially hidden
    expect(wrapper.find('#edit-repeat-interval').exists()).toBe(false)

    await wrapper.find('#edit-category').setValue('repeating')

    expect(wrapper.find('#edit-repeat-interval').exists()).toBe(true)
    expect(wrapper.find('#edit-repeat-until').exists()).toBe(true)
  })

  // --- Quick-select buttons ---

  it('shows quick-select buttons for repeat_interval when category is repeating', () => {
    const wrapper = mount(TaskEditModal, { props: { task: repeatingTask } })
    const buttons = wrapper.findAll('button').filter((b) => ['15m', '1h', '1d', '1w'].includes(b.text()))
    expect(buttons).toHaveLength(4)
  })

  it('quick-select button populates repeat_interval', async () => {
    const wrapper = mount(TaskEditModal, { props: { task: repeatingTask } })
    const btn1h = wrapper.findAll('button').find((b) => b.text() === '1h')!
    await btn1h.trigger('click')

    const input = wrapper.find('#edit-repeat-interval').element as HTMLInputElement
    expect(input.value).toBe('1h')
  })

  // --- Repeat interval value ---

  it('repeat_interval shows current value from task', () => {
    const wrapper = mount(TaskEditModal, { props: { task: repeatingTask } })
    const input = wrapper.find('#edit-repeat-interval').element as HTMLInputElement
    expect(input.value).toBe('1d')
  })

  // --- Completed at / execute_at conditional display ---

  it('shows "Completed at" with formatted updated_at for review tasks', () => {
    const reviewTask: TaskData = { ...task, status: 'review', updated_at: '2026-02-10T15:30:00Z' }
    const wrapper = mount(TaskEditModal, { props: { task: reviewTask } })

    expect(wrapper.text()).toContain('Completed at')
    expect(wrapper.find('#edit-execute-at').exists()).toBe(false)
  })

  it('shows "Completed at" with formatted updated_at for completed tasks', () => {
    const completedTask: TaskData = { ...task, status: 'completed', updated_at: '2026-02-10T16:00:00Z' }
    const wrapper = mount(TaskEditModal, { props: { task: completedTask } })

    expect(wrapper.text()).toContain('Completed at')
    expect(wrapper.find('#edit-execute-at').exists()).toBe(false)
  })

  it('shows execute_at picker for pending tasks (not "Completed at")', () => {
    const pendingTask: TaskData = { ...task, status: 'pending' }
    const wrapper = mount(TaskEditModal, { props: { task: pendingTask } })

    expect(wrapper.text()).not.toContain('Completed at')
    expect(wrapper.find('#edit-execute-at').exists()).toBe(true)
  })

  it('shows execute_at picker for scheduled tasks (not "Completed at")', () => {
    const scheduledTask: TaskData = { ...task, status: 'scheduled' }
    const wrapper = mount(TaskEditModal, { props: { task: scheduledTask } })

    expect(wrapper.text()).not.toContain('Completed at')
    expect(wrapper.find('#edit-execute-at').exists()).toBe(true)
  })

  // --- Delete button ---

  it('shows a delete button styled as danger', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const deleteBtn = wrapper.findAll('button[type="button"]').find((b) => b.text() === 'Delete')
    expect(deleteBtn).toBeDefined()
    expect(deleteBtn!.classes()).toContain('text-red-600')
  })

  it('emits delete when delete button is clicked', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const deleteBtn = wrapper.findAll('button[type="button"]').find((b) => b.text() === 'Delete')!
    await deleteBtn.trigger('click')

    expect(wrapper.emitted('delete')).toHaveLength(1)
  })

  // --- Two-column grid layout ---

  it('has two-column grid class on the layout container', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const grid = wrapper.find('.grid')
    expect(grid.exists()).toBe(true)
    expect(grid.classes()).toContain('md:grid-cols-[1fr_2fr]')
  })

  // --- Description textarea rows ---

  it('description textarea has rows="8" and min-h for flex-grow', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const textarea = wrapper.find('#edit-description')
    expect(textarea.attributes('rows')).toBe('8')
    expect(textarea.classes()).toContain('h-full')
    expect(textarea.classes()).toContain('min-h-[8rem]')
  })

  it('right column uses flex layout with description container as flex-1', () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    const textarea = wrapper.find('#edit-description')
    const descContainer = textarea.element.parentElement!
    expect(descContainer.classList.contains('flex-1')).toBe(true)
    expect(descContainer.classList.contains('flex')).toBe(true)
    expect(descContainer.classList.contains('flex-col')).toBe(true)
    const rightCol = descContainer.parentElement!
    expect(rightCol.classList.contains('flex')).toBe(true)
    expect(rightCol.classList.contains('flex-col')).toBe(true)
    expect(rightCol.classList.contains('gap-4')).toBe(true)
  })

  // --- Backdrop dismiss with dirty guard ---

  it('emits cancel on backdrop click when form is clean', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    // Simulate clicking on the dialog element itself (backdrop)
    await wrapper.find('dialog').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('shows confirm dialog on backdrop click when form is dirty', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = mount(TaskEditModal, { props: { task } })

    // Make form dirty
    await wrapper.find('#edit-title').setValue('Changed title')

    // Simulate backdrop click
    await wrapper.find('dialog').trigger('click')

    expect(confirmSpy).toHaveBeenCalledWith('Discard unsaved changes?')
    // Should NOT emit cancel since confirm returned false
    expect(wrapper.emitted('cancel')).toBeUndefined()
    confirmSpy.mockRestore()
  })

  it('emits cancel on backdrop click when dirty and user confirms discard', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(TaskEditModal, { props: { task } })

    await wrapper.find('#edit-title').setValue('Changed title')
    await wrapper.find('dialog').trigger('click')

    expect(confirmSpy).toHaveBeenCalled()
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    confirmSpy.mockRestore()
  })

  it('shows confirm dialog on Escape key when form is dirty', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = mount(TaskEditModal, { props: { task } })

    await wrapper.find('#edit-title').setValue('Changed title')
    await wrapper.find('dialog').trigger('cancel')

    expect(confirmSpy).toHaveBeenCalledWith('Discard unsaved changes?')
    expect(wrapper.emitted('cancel')).toBeUndefined()
    confirmSpy.mockRestore()
  })

  it('emits cancel on Escape key when form is clean', async () => {
    const wrapper = mount(TaskEditModal, { props: { task } })
    await wrapper.find('dialog').trigger('cancel')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})
