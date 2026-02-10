import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskOutputModal from '../TaskOutputModal.vue'

describe('TaskOutputModal', () => {
  it('displays the task title as header', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Fix auth bug', output: 'Some output' },
    })
    expect(wrapper.text()).toContain('Fix auth bug')
  })

  it('displays output in a monospace pre block', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'Line 1\nLine 2\nLine 3' },
    })
    const pre = wrapper.find('pre')
    expect(pre.exists()).toBe(true)
    expect(pre.text()).toContain('Line 1')
    expect(pre.text()).toContain('Line 3')
    expect(pre.classes()).toContain('font-mono')
  })

  it('shows "No output available" when output is null', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: null },
    })
    expect(wrapper.find('pre').exists()).toBe(false)
    expect(wrapper.text()).toContain('No output available')
  })

  it('shows "No output available" when output is empty string', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: '' },
    })
    expect(wrapper.find('pre').exists()).toBe(false)
    expect(wrapper.text()).toContain('No output available')
  })

  it('emits close when Close button is clicked', async () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'output' },
    })
    const closeBtn = wrapper.findAll('button').find((b) => b.text() === 'Close')!
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('emits close when X button is clicked', async () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'output' },
    })
    const xBtn = wrapper.find('button[aria-label="Close"]')
    await xBtn.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
