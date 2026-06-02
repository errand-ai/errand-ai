import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PluginPollIntervalSettings from '../settings/PluginPollIntervalSettings.vue'

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

describe('PluginPollIntervalSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the initial value', () => {
    const wrapper = mount(PluginPollIntervalSettings, {
      props: { initialValue: 21600, saveSettings: vi.fn() },
    })
    const input = wrapper.find('[data-testid="plugin-poll-interval-input"]').element as HTMLInputElement
    expect(input.value).toBe('21600')
  })

  it('shows "Polling disabled" when value is 0', async () => {
    const wrapper = mount(PluginPollIntervalSettings, {
      props: { initialValue: 21600, saveSettings: vi.fn() },
    })
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('0')
    expect(wrapper.find('[data-testid="plugin-poll-disabled-hint"]').exists()).toBe(true)
  })

  it('rejects negative values with an error message', async () => {
    const saveSettings = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(PluginPollIntervalSettings, {
      props: { initialValue: 21600, saveSettings },
    })
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('-1')
    await wrapper.find('[data-testid="plugin-poll-save"]').trigger('click')
    await flushPromises()
    expect(saveSettings).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="plugin-poll-error"]').exists()).toBe(true)
  })

  it('saves a positive integer via saveSettings', async () => {
    const saveSettings = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(PluginPollIntervalSettings, {
      props: { initialValue: 21600, saveSettings },
    })
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('14400')
    await wrapper.find('[data-testid="plugin-poll-save"]').trigger('click')
    await flushPromises()
    expect(saveSettings).toHaveBeenCalledWith({ plugin_poll_interval_seconds: 14400 })
  })

  it('saves zero to disable polling', async () => {
    const saveSettings = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(PluginPollIntervalSettings, {
      props: { initialValue: 21600, saveSettings },
    })
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('0')
    await wrapper.find('[data-testid="plugin-poll-save"]').trigger('click')
    await flushPromises()
    expect(saveSettings).toHaveBeenCalledWith({ plugin_poll_interval_seconds: 0 })
  })
})
