import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import CloudServicePage from '../CloudServicePage.vue'

// Mock vue-sonner
const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/settings/cloud', component: CloudServicePage },
    ],
  })
  return router
}

function stubFetch(status: object) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(status),
  })
}

describe('CloudServicePage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    toastMock.success.mockClear()
    toastMock.error.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders not-connected state with Connect button', async () => {
    vi.stubGlobal('fetch', stubFetch({ status: 'not_configured' }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-not-connected"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-connect-btn"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-connect-btn"]').text()).toContain('Connect')
  })

  it('renders connected state with Disconnect button', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      email: 'user@example.com',
      endpoints: [],
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-connected"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-disconnect-btn"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Connected')
    expect(wrapper.text()).toContain('user@example.com')
  })

  it('renders error state with Reconnect button', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'error',
      detail: 'Authentication expired',
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-reconnect-btn"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Authentication expired')
  })

  it('displays endpoints when connected with endpoints', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [
        { integration: 'slack', endpoint_type: 'events', url: 'https://cloud.test/hook/t1', token: 't1' },
        { integration: 'slack', endpoint_type: 'commands', url: 'https://cloud.test/hook/t2', token: 't2' },
      ],
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-endpoints"]').exists()).toBe(true)
    const copyBtns = wrapper.findAll('[data-testid="copy-endpoint-btn"]')
    expect(copyBtns.length).toBe(2)
    expect(wrapper.text()).toContain('https://cloud.test/hook/t1')
    expect(wrapper.text()).toContain('https://cloud.test/hook/t2')
  })

  it('shows Slack not enabled message when connected without Slack configured', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      slack_configured: false,
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-no-slack"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Enable Slack')
  })

  it('shows registering message when connected with Slack but no endpoints yet', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      slack_configured: true,
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-registering"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Endpoints are being registered')
  })

  it('shows error toast when OAuth error query param is present', async () => {
    vi.stubGlobal('fetch', stubFetch({ status: 'not_configured' }))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/settings/cloud', component: CloudServicePage },
      ],
    })
    await router.push('/settings/cloud?error=access_denied')
    await router.isReady()

    mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(toastMock.error).toHaveBeenCalledWith('access_denied')
  })

  it('shows endpoint error instead of registering message', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      slack_configured: true,
      endpoint_error: { detail: 'Active subscription required' },
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-endpoint-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Active subscription required')
    expect(wrapper.find('[data-testid="cloud-registering"]').exists()).toBe(false)
  })

  it('fires toast on endpoint registration error', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      slack_configured: true,
      endpoint_error: { detail: 'Active subscription required' },
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(toastMock.error).toHaveBeenCalledWith(
      'Endpoint registration failed: Active subscription required',
    )
  })

  it('displays subscription expiry date', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      subscription: { active: true, expires_at: '2026-04-15T00:00:00Z' },
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-subscription-expiry"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Subscription expires')
    expect(wrapper.text()).toContain('2026')
  })

  it('shows warning when subscription is inactive', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      subscription: { active: false, expires_at: '2025-01-01T00:00:00Z' },
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-subscription-warning"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('subscription has expired')
  })

  it('does not show subscription info when absent', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-subscription-expiry"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="cloud-subscription-warning"]').exists()).toBe(false)
  })

  it('shows Manage Account link when connected', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    const link = wrapper.find('[data-testid="cloud-manage-account-btn"]')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://errand.cloud')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toBe('noopener noreferrer')
    expect(link.text()).toContain('Manage Account')
  })

  it('does not show Manage Account link when not connected', async () => {
    vi.stubGlobal('fetch', stubFetch({ status: 'not_configured' }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-manage-account-btn"]').exists()).toBe(false)
  })

  it('calls disconnect API and refreshes status', async () => {
    const fetchMock = vi.fn()
      // First call: initial status fetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          status: 'connected',
          tenant_id: 'tenant-abc',
          endpoints: [],
        }),
      })
      // Second call: disconnect POST
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      })
      // Third call: status refresh after disconnect
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'not_configured' }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    const disconnectBtn = wrapper.find('[data-testid="cloud-disconnect-btn"]')
    await disconnectBtn.trigger('click')
    await flushPromises()

    // Verify disconnect was called
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const disconnectCall = fetchMock.mock.calls[1]
    expect(disconnectCall[0]).toBe('/api/cloud/auth/disconnect')
    expect(disconnectCall[1].method).toBe('POST')

    expect(toastMock.success).toHaveBeenCalledWith('Disconnected from Errand Cloud')
  })
})
