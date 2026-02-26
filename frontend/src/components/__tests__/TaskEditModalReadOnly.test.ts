import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskEditModal from '../TaskEditModal.vue'
import type { TaskData } from '../../composables/useApi'

vi.mock('../../composables/useApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../composables/useApi')>()
  return {
    ...actual,
    fetchTags: vi.fn().mockResolvedValue([]),
    fetchTaskProfiles: vi.fn().mockResolvedValue([]),
  }
})

const baseTask: TaskData = {
  id: '1',
  title: 'Test task',
  description: 'A description',
  status: 'pending',
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
  tags: ['tag1'],
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
}

describe('TaskEditModal — read-only mode', () => {
  it('disables all form inputs when readOnly is true', () => {
    const wrapper = mount(TaskEditModal, { props: { task: baseTask, readOnly: true } })

    expect((wrapper.find('#edit-title').element as HTMLInputElement).disabled).toBe(true)
    expect((wrapper.find('#edit-description').element as HTMLTextAreaElement).disabled).toBe(true)
    expect((wrapper.find('#edit-status').element as HTMLSelectElement).disabled).toBe(true)
    expect((wrapper.find('#edit-category').element as HTMLSelectElement).disabled).toBe(true)
  })

  it('hides Save and Delete buttons when readOnly is true', () => {
    const wrapper = mount(TaskEditModal, { props: { task: baseTask, readOnly: true } })

    const buttons = wrapper.findAll('button')
    const buttonTexts = buttons.map((b) => b.text())
    expect(buttonTexts).not.toContain('Save')
    expect(buttonTexts).not.toContain('Delete')
  })

  it('shows Close button instead of Cancel when readOnly is true', () => {
    const wrapper = mount(TaskEditModal, { props: { task: baseTask, readOnly: true } })

    const buttons = wrapper.findAll('button')
    const buttonTexts = buttons.map((b) => b.text())
    expect(buttonTexts).toContain('Close')
    expect(buttonTexts).not.toContain('Cancel')
  })

  it('hides tag remove buttons when readOnly is true', () => {
    const wrapper = mount(TaskEditModal, { props: { task: baseTask, readOnly: true } })

    // Tags should be displayed but without remove buttons
    expect(wrapper.text()).toContain('tag1')
    const tagRemoveButtons = wrapper.findAll('.inline-flex button')
    expect(tagRemoveButtons).toHaveLength(0)
  })

  it('hides the tag input when readOnly is true', () => {
    const wrapper = mount(TaskEditModal, { props: { task: baseTask, readOnly: true } })
    const tagInput = wrapper.find('input[placeholder="Add tag..."]')
    expect(tagInput.exists()).toBe(false)
  })

  it('inputs are enabled when readOnly is false', () => {
    const wrapper = mount(TaskEditModal, { props: { task: baseTask, readOnly: false } })

    expect((wrapper.find('#edit-title').element as HTMLInputElement).disabled).toBe(false)
    expect((wrapper.find('#edit-description').element as HTMLTextAreaElement).disabled).toBe(false)
  })

  it('shows Save and Delete buttons when readOnly is false', () => {
    const wrapper = mount(TaskEditModal, { props: { task: baseTask, readOnly: false } })

    const buttons = wrapper.findAll('button')
    const buttonTexts = buttons.map((b) => b.text())
    expect(buttonTexts).toContain('Save')
    expect(buttonTexts).toContain('Delete')
  })
})

describe('TaskEditModal — completed task read-only mode', () => {
  it('completed task with readOnly shows disabled fields and no Save/Delete', () => {
    const completedTask: TaskData = { ...baseTask, status: 'completed' }
    const wrapper = mount(TaskEditModal, { props: { task: completedTask, readOnly: true } })

    expect((wrapper.find('#edit-title').element as HTMLInputElement).disabled).toBe(true)
    expect((wrapper.find('#edit-description').element as HTMLTextAreaElement).disabled).toBe(true)
    const buttons = wrapper.findAll('button')
    const buttonTexts = buttons.map((b) => b.text())
    expect(buttonTexts).not.toContain('Save')
    expect(buttonTexts).not.toContain('Delete')
    expect(buttonTexts).toContain('Close')
  })
})

describe('TaskEditModal — running task is read-only in KanbanBoard context', () => {
  it('shows readOnly behavior for running tasks when readOnly prop is passed', () => {
    const runningTask: TaskData = { ...baseTask, status: 'running' }
    const wrapper = mount(TaskEditModal, { props: { task: runningTask, readOnly: true } })

    expect((wrapper.find('#edit-title').element as HTMLInputElement).disabled).toBe(true)
    const buttons = wrapper.findAll('button')
    const buttonTexts = buttons.map((b) => b.text())
    expect(buttonTexts).not.toContain('Save')
    expect(buttonTexts).not.toContain('Delete')
  })
})
