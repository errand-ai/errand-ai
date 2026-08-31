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

const { mockFetchWebhookTriggers } = vi.hoisted(() => {
  return { mockFetchWebhookTriggers: vi.fn().mockResolvedValue([]) }
})
vi.mock('../../../composables/useApi', () => ({
  fetchWebhookTriggers: (...args: any[]) => mockFetchWebhookTriggers(...args),
}))

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

  it('displays per-trigger Jira/GitHub webhook URLs in the endpoints section', async () => {
    mockFetchWebhookTriggers.mockResolvedValueOnce([
      {
        id: 't-jira', name: 'Jira Bugs', source: 'jira', enabled: true, has_secret: true,
        filters: {}, actions: {}, profile_id: null, task_prompt: null,
        cloud_webhook_url: 'https://cloud.test/hook/jira1',
      },
      {
        id: 't-gh', name: 'GH Issues', source: 'github', enabled: true, has_secret: true,
        filters: {}, actions: {}, profile_id: null, task_prompt: null,
        cloud_webhook_url: 'https://cloud.test/hook/gh1',
      },
    ])
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

    const rows = wrapper.findAll('[data-testid="trigger-endpoint-row"]')
    expect(rows.length).toBe(2)
    expect(wrapper.text()).toContain('https://cloud.test/hook/jira1')
    expect(wrapper.text()).toContain('https://cloud.test/hook/gh1')
    expect(wrapper.findAll('[data-testid="copy-trigger-url-btn"]').length).toBe(2)
  })

  it('shows "Cloud not connected" placeholder for trigger when not connected to cloud', async () => {
    mockFetchWebhookTriggers.mockResolvedValueOnce([
      {
        id: 't-jira', name: 'Jira Bugs', source: 'jira', enabled: true, has_secret: true,
        filters: {}, actions: {}, profile_id: null, task_prompt: null,
        cloud_webhook_url: null,
      },
    ])
    vi.stubGlobal('fetch', stubFetch({ status: 'not_configured' }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="trigger-cloud-not-connected"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trigger-registration-failed"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="copy-trigger-url-btn"]').exists()).toBe(false)
  })

  it('shows "Registration failed" placeholder for trigger without cloud_webhook_url when connected', async () => {
    mockFetchWebhookTriggers.mockResolvedValueOnce([
      {
        id: 't-jira', name: 'Jira Bugs', source: 'jira', enabled: true, has_secret: true,
        filters: {}, actions: {}, profile_id: null, task_prompt: null,
        cloud_webhook_url: null,
      },
    ])
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

    expect(wrapper.find('[data-testid="trigger-registration-failed"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="copy-trigger-url-btn"]').exists()).toBe(false)
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
    expect(wrapper.text()).toContain('Configure Slack, Jira, or GitHub')
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

    expect(wrapper.find('[data-testid="cloud-endpoint-error-banner"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Active subscription required')
    expect(wrapper.find('[data-testid="cloud-registering"]').exists()).toBe(false)
  })

  it('keeps the global endpoint-error banner visible when triggers exist (regression)', async () => {
    // Previous behavior hid the section-level error block whenever any trigger
    // row rendered, so users lost the only persistent error detail. The banner
    // now sits above the rows and is always shown when endpoint_error is set.
    mockFetchWebhookTriggers.mockResolvedValueOnce([
      {
        id: 't-jira', name: 'Jira Bugs', source: 'jira', enabled: true, has_secret: true,
        filters: {}, actions: {}, profile_id: null, task_prompt: null,
        cloud_webhook_url: null,
      },
    ])
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      endpoint_error: { detail: 'Active subscription required' },
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-endpoint-error-banner"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Active subscription required')
    // Trigger rows still render too — banner is additive, not exclusive.
    expect(wrapper.find('[data-testid="trigger-endpoint-row"]').exists()).toBe(true)
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

  it('shows amber retry payment warning when final_attempt is false', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      subscription: {
        active: true,
        expires_at: '2026-04-15T00:00:00Z',
        payment_warning: {
          alert: 'payment_failed',
          plan: 'monthly',
          attempt_count: 1,
          next_retry_at: '2026-03-12T14:00:00Z',
          final_attempt: false,
        },
      },
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    const warning = wrapper.find('[data-testid="cloud-payment-warning"]')
    expect(warning.exists()).toBe(true)
    expect(warning.text()).toContain('Payment failed — retrying')
    expect(warning.text()).toContain('12 Mar 2026')
    expect(warning.classes()).toContain('text-amber-600')
    expect(warning.classes()).not.toContain('text-red-600')
  })

  it('shows red expired payment warning when final_attempt is true', async () => {
    vi.stubGlobal('fetch', stubFetch({
      status: 'connected',
      tenant_id: 'tenant-abc',
      endpoints: [],
      subscription: {
        active: false,
        expires_at: '2026-03-01T00:00:00Z',
        payment_warning: {
          alert: 'payment_failed',
          plan: 'monthly',
          attempt_count: 4,
          next_retry_at: null,
          final_attempt: true,
        },
      },
    }))
    const router = makeRouter()
    await router.push('/settings/cloud')
    await router.isReady()

    const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
    await flushPromises()

    const warning = wrapper.find('[data-testid="cloud-payment-warning"]')
    expect(warning.exists()).toBe(true)
    expect(warning.text()).toContain('Payment failed — subscription expired')
    expect(warning.classes()).toContain('text-red-600')
  })

  it('does not show payment warning when absent', async () => {
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

    expect(wrapper.find('[data-testid="cloud-payment-warning"]').exists()).toBe(false)
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
    let cloudStatus = 'connected'
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/cloud/status') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: cloudStatus, tenant_id: 'tenant-abc', endpoints: [] }),
        })
      }
      if (url === '/api/cloud/auth/device/status') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'none' }) })
      }
      if (url === '/api/cloud/auth/disconnect') {
        cloudStatus = 'not_configured'
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      throw new Error(`unexpected fetch: ${url}`)
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

    const disconnectCall = fetchMock.mock.calls.find(
      (c: any[]) => c[0] === '/api/cloud/auth/disconnect',
    )
    expect(disconnectCall).toBeDefined()
    expect(disconnectCall![1].method).toBe('POST')
    expect(toastMock.success).toHaveBeenCalledWith('Disconnected from Errand Cloud')
    expect(wrapper.find('[data-testid="cloud-not-connected"]').exists()).toBe(true)
  })

  describe('device authorization grant', () => {
    const GRANT = {
      user_code: 'JHBW-PMHF',
      verification_uri: 'https://errand.cloud/auth/tenant/device',
      verification_uri_complete: 'https://errand.cloud/auth/tenant/device?user_code=JHBW-PMHF',
      expires_in: 600,
    }

    /** Routes by URL so device status can be advanced independently of cloud status. */
    function routedFetch(opts: {
      cloud?: object
      deviceStatuses?: object[]
      startResponse?: { ok: boolean; body?: object }
    }) {
      const deviceStatuses = [...(opts.deviceStatuses ?? [{ status: 'none' }])]
      return vi.fn().mockImplementation((url: string) => {
        if (url === '/api/cloud/status') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(opts.cloud ?? { status: 'not_configured' }),
          })
        }
        if (url === '/api/cloud/auth/device/status') {
          const next = deviceStatuses.length > 1 ? deviceStatuses.shift() : deviceStatuses[0]
          return Promise.resolve({ ok: true, json: () => Promise.resolve(next) })
        }
        if (url === '/api/cloud/auth/device') {
          const r = opts.startResponse ?? { ok: true, body: GRANT }
          return Promise.resolve({ ok: r.ok, json: () => Promise.resolve(r.body ?? {}) })
        }
        throw new Error(`unexpected fetch: ${url}`)
      })
    }

    async function mountPage() {
      const router = makeRouter()
      await router.push('/settings/cloud')
      await router.isReady()
      const wrapper = mount(CloudServicePage, { global: { plugins: [router] } })
      await flushPromises()
      return wrapper
    }

    it('shows the verification code and link instead of opening a popup', async () => {
      const openSpy = vi.fn()
      vi.stubGlobal('open', openSpy)
      const fetchMock = routedFetch({})
      vi.stubGlobal('fetch', fetchMock)

      const wrapper = await mountPage()
      await wrapper.find('[data-testid="cloud-connect-btn"]').trigger('click')
      await flushPromises()

      expect(openSpy).not.toHaveBeenCalled()
      const startCall = fetchMock.mock.calls.find((c: any[]) => c[0] === '/api/cloud/auth/device')
      expect(startCall![1].method).toBe('POST')

      expect(wrapper.find('[data-testid="cloud-device-grant"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="cloud-device-code"]').text()).toBe('JHBW-PMHF')

      const link = wrapper.find('[data-testid="cloud-device-link"]')
      // The completion URI carries the code, so a click on this machine needs no retyping,
      // while the bare code stays visible for a different device.
      expect(link.attributes('href')).toBe(GRANT.verification_uri_complete)
      expect(link.text()).toBe(GRANT.verification_uri)
    })

    it('reflects completion without a manual reload', async () => {
      vi.useFakeTimers()
      try {
        const fetchMock = routedFetch({
          deviceStatuses: [{ status: 'none' }, { status: 'connected' }],
        })
        vi.stubGlobal('fetch', fetchMock)

        const wrapper = await mountPage()
        await wrapper.find('[data-testid="cloud-connect-btn"]').trigger('click')
        await flushPromises()
        expect(wrapper.find('[data-testid="cloud-device-grant"]').exists()).toBe(true)

        await vi.advanceTimersByTimeAsync(3100)
        await flushPromises()

        expect(wrapper.find('[data-testid="cloud-device-grant"]').exists()).toBe(false)
        expect(toastMock.success).toHaveBeenCalledWith('Connected to Errand Cloud')
      } finally {
        vi.useRealTimers()
      }
    })

    it.each([
      ['denied', 'refused'],
      ['expired', 'expired'],
      ['error', 'failed'],
    ])('reflects a %s outcome distinctly', async (status, phrase) => {
      vi.useFakeTimers()
      try {
        const fetchMock = routedFetch({
          deviceStatuses: [{ status: 'none' }, { status }],
        })
        vi.stubGlobal('fetch', fetchMock)

        const wrapper = await mountPage()
        await wrapper.find('[data-testid="cloud-connect-btn"]').trigger('click')
        await flushPromises()

        await vi.advanceTimersByTimeAsync(3100)
        await flushPromises()

        expect(wrapper.find('[data-testid="cloud-device-grant"]').exists()).toBe(false)
        const failure = wrapper.find('[data-testid="cloud-device-failure"]')
        expect(failure.exists()).toBe(true)
        expect(failure.text().toLowerCase()).toContain(phrase)
        expect(wrapper.find('[data-testid="cloud-connect-btn"]').exists()).toBe(true)
      } finally {
        vi.useRealTimers()
      }
    })

    it('restores a pending grant on reload', async () => {
      const fetchMock = routedFetch({
        deviceStatuses: [{ status: 'pending', ...GRANT }],
      })
      vi.stubGlobal('fetch', fetchMock)

      const wrapper = await mountPage()

      expect(wrapper.find('[data-testid="cloud-device-grant"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="cloud-device-code"]').text()).toBe('JHBW-PMHF')
    })

    it('reports a failure to start the grant', async () => {
      const fetchMock = routedFetch({ startResponse: { ok: false } })
      vi.stubGlobal('fetch', fetchMock)

      const wrapper = await mountPage()
      await wrapper.find('[data-testid="cloud-connect-btn"]').trigger('click')
      await flushPromises()

      expect(toastMock.error).toHaveBeenCalledWith('Failed to start cloud connection')
      expect(wrapper.find('[data-testid="cloud-device-grant"]').exists()).toBe(false)
    })
  })
})
