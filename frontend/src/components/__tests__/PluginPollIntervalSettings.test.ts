import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../../stores/auth'
import PluginPollIntervalSettings from '../settings/PluginPollIntervalSettings.vue'

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

// Post-Wave-2 the component self-loads its interval from GET /api/settings and
// saves via PUT /api/settings (no props). These helpers drive that fetch surface.
function stubFetch(interval: number = 21600) {
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit = {}) => {
    if (url === '/api/settings' && (options.method ?? 'GET') === 'GET') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ plugin_poll_interval_seconds: interval }),
      })
    }
    // PUT (save) — echo ok.
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Extract the parsed body of the first PUT /api/settings call. */
function lastSaveBody(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown> | null {
  const put = fetchMock.mock.calls.find(
    ([url, opts]) => url === '/api/settings' && (opts?.method) === 'PUT',
  )
  return put ? JSON.parse((put[1] as RequestInit).body as string) : null
}

async function mountLoaded(interval = 21600) {
  const fetchMock = stubFetch(interval)
  const wrapper = mount(PluginPollIntervalSettings)
  await flushPromises()
  return { wrapper, fetchMock }
}

describe('PluginPollIntervalSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().setToken(
      `${btoa(JSON.stringify({ alg: 'none' }))}.${btoa(JSON.stringify({ name: 'a' }))}.x`,
    )
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('loads and renders the current value', async () => {
    const { wrapper } = await mountLoaded(21600)
    const input = wrapper.find('[data-testid="plugin-poll-interval-input"]').element as HTMLInputElement
    expect(input.value).toBe('21600')
  })

  it('shows a loading placeholder before the initial load resolves (no flash of the default)', () => {
    stubFetch(21600)
    const wrapper = mount(PluginPollIntervalSettings)
    // Synchronously, before flushPromises: loading state, input not yet rendered.
    expect(wrapper.find('[data-testid="plugin-poll-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plugin-poll-interval-input"]').exists()).toBe(false)
  })

  it('surfaces a load error when GET /api/settings fails (value may be stale)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: () => Promise.resolve({ detail: 'Admin role required' }) }),
    )
    const wrapper = mount(PluginPollIntervalSettings)
    await flushPromises()
    expect(wrapper.find('[data-testid="plugin-poll-error"]').exists()).toBe(true)
  })

  it('shows "Polling disabled" when value is 0', async () => {
    const { wrapper } = await mountLoaded()
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('0')
    expect(wrapper.find('[data-testid="plugin-poll-disabled-hint"]').exists()).toBe(true)
  })

  it('rejects negative values with an error message', async () => {
    const { wrapper, fetchMock } = await mountLoaded()
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('-1')
    await wrapper.find('[data-testid="plugin-poll-save"]').trigger('click')
    await flushPromises()
    expect(lastSaveBody(fetchMock)).toBeNull()
    expect(wrapper.find('[data-testid="plugin-poll-error"]').exists()).toBe(true)
  })

  it('saves a positive integer via PUT /api/settings', async () => {
    const { wrapper, fetchMock } = await mountLoaded()
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('14400')
    await wrapper.find('[data-testid="plugin-poll-save"]').trigger('click')
    await flushPromises()
    expect(lastSaveBody(fetchMock)).toEqual({ plugin_poll_interval_seconds: 14400 })
  })

  it('saves zero to disable polling', async () => {
    const { wrapper, fetchMock } = await mountLoaded()
    await wrapper.find('[data-testid="plugin-poll-interval-input"]').setValue('0')
    await wrapper.find('[data-testid="plugin-poll-save"]').trigger('click')
    await flushPromises()
    expect(lastSaveBody(fetchMock)).toEqual({ plugin_poll_interval_seconds: 0 })
  })
})
