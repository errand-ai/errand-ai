import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TaskForm from '../TaskForm.vue'
import { useTaskStore } from '../../stores/tasks'

describe('TaskForm', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has placeholder text "New task..."', () => {
    const wrapper = mount(TaskForm)
    const input = wrapper.find('input')
    expect(input.attributes('placeholder')).toBe('New task...')
  })

  it('calls store addTask with input text on submission', async () => {
    const wrapper = mount(TaskForm)
    const store = useTaskStore()
    store.addTask = vi.fn().mockResolvedValue(undefined)

    await wrapper.find('input').setValue('New task')
    await wrapper.find('form').trigger('submit')

    expect(store.addTask).toHaveBeenCalledWith('New task')
  })

  it('shows validation error for empty input without calling store', async () => {
    const wrapper = mount(TaskForm)
    const store = useTaskStore()
    store.addTask = vi.fn()

    await wrapper.find('form').trigger('submit')

    expect(wrapper.text()).toContain('Task cannot be empty')
    expect(store.addTask).not.toHaveBeenCalled()
  })

  it('clears input after successful submission', async () => {
    const wrapper = mount(TaskForm)
    const store = useTaskStore()
    store.addTask = vi.fn().mockResolvedValue(undefined)

    await wrapper.find('input').setValue('New task')
    await wrapper.find('form').trigger('submit')

    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('')
  })
})
