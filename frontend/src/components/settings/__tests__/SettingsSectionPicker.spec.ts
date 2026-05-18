import { describe, it, expect, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import SettingsSectionPicker from '../SettingsSectionPicker.vue'

const sections = [
  { id: 'agent', label: 'Agent Configuration', to: '/settings/agent' },
  { id: 'tasks', label: 'Task Management', to: '/settings/tasks' },
  { id: 'security', label: 'Security', to: '/settings/security' },
]

const wrappers: VueWrapper[] = []

function makeWrapper(activeRoute = '/settings/tasks') {
  const wrapper = mount(SettingsSectionPicker, {
    props: { sections, activeRoute },
    attachTo: document.body,
  })
  wrappers.push(wrapper)
  return wrapper
}

afterEach(() => {
  while (wrappers.length) {
    wrappers.pop()?.unmount()
  }
})

describe('SettingsSectionPicker', () => {
  it('renders the active label in the closed-state button', () => {
    const wrapper = makeWrapper('/settings/tasks')
    const button = wrapper.get('[data-testid="settings-section-picker-button"]')
    expect(button.text()).toContain('Task Management')
    expect(button.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[data-testid="settings-section-picker-panel"]').exists()).toBe(false)
  })

  it('opens the panel on click and exposes aria-expanded', async () => {
    const wrapper = makeWrapper()
    await wrapper.get('[data-testid="settings-section-picker-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="settings-section-picker-panel"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="settings-section-picker-button"]').attributes('aria-expanded')).toBe('true')
    const options = wrapper.findAll('[role="option"]')
    expect(options).toHaveLength(sections.length)
  })

  it('emits change with the selected route and closes', async () => {
    const wrapper = makeWrapper()
    await wrapper.get('[data-testid="settings-section-picker-button"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="settings-section-picker-option-security"]').trigger('click')
    expect(wrapper.emitted('change')).toEqual([['/settings/security']])
    expect(wrapper.find('[data-testid="settings-section-picker-panel"]').exists()).toBe(false)
  })

  it('closes the panel on Escape', async () => {
    const wrapper = makeWrapper()
    await wrapper.get('[data-testid="settings-section-picker-button"]').trigger('click')
    await flushPromises()
    const firstOption = wrapper.get('[role="option"]')
    await firstOption.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[data-testid="settings-section-picker-panel"]').exists()).toBe(false)
  })

  it('supports keyboard navigation (ArrowDown + Enter)', async () => {
    const wrapper = makeWrapper('/settings/agent')
    const button = wrapper.get('[data-testid="settings-section-picker-button"]')
    await button.trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(wrapper.find('[data-testid="settings-section-picker-panel"]').exists()).toBe(true)
    const options = wrapper.findAll('[role="option"]')
    await options[0].trigger('keydown', { key: 'ArrowDown' })
    await options[1].trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('change')).toEqual([['/settings/tasks']])
  })

  it('Enter on the trigger toggles the panel', async () => {
    const wrapper = makeWrapper()
    const button = wrapper.get('[data-testid="settings-section-picker-button"]')
    await button.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.find('[data-testid="settings-section-picker-panel"]').exists()).toBe(true)
    await button.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.find('[data-testid="settings-section-picker-panel"]').exists()).toBe(false)
  })

  it('ArrowDown on the trigger opens to the first option', async () => {
    const wrapper = makeWrapper('/settings/security')
    const button = wrapper.get('[data-testid="settings-section-picker-button"]')
    await button.trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.findAll('[role="option"]')[0].element)
  })

  it('returns focus to the trigger after Escape', async () => {
    const wrapper = makeWrapper()
    const button = wrapper.get('[data-testid="settings-section-picker-button"]')
    await button.trigger('click')
    await flushPromises()
    await wrapper.get('[role="option"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(document.activeElement).toBe(button.element)
  })
})
