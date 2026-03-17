import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import TaskGeneratorsPage from '../settings/TaskGeneratorsPage.vue'

// Mock vue-sonner
const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

// Mock useApi
vi.mock('../../composables/useApi', () => ({
  fetchTaskProfiles: vi.fn().mockResolvedValue([
    { id: 'profile-1', name: 'Profile A' },
    { id: 'profile-2', name: 'Profile B' },
  ]),
}))

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const adminToken = fakeJwt({
  name: 'Admin',
  resource_access: { 'errand': { roles: ['admin'] } },
})

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/settings/task-generators', component: TaskGeneratorsPage },
      { path: '/settings/integrations', component: { template: '<div>Integrations</div>' } },
    ],
  })
}

// Default fetch mock: email credentials configured, no generator
function setupFetch(overrides: Record<string, any> = {}) {
  const defaults = {
    generatorStatus: 404,
    generatorData: null,
    platforms: [{ id: 'email', label: 'Email', status: 'connected' }],
  }
  const config = { ...defaults, ...overrides }

  return vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
    if (url === '/api/task-generators/email' && (!opts || opts.method !== 'PUT')) {
      if (config.generatorStatus === 404) {
        return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) })
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(config.generatorData) })
    }
    if (url === '/api/task-generators/email' && opts?.method === 'PUT') {
      const body = JSON.parse(opts.body as string)
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          id: 'gen-1',
          type: 'email',
          enabled: body.enabled,
          profile_id: body.profile_id,
          config: body.config,
          created_at: '2024-01-01T00:00:00',
          updated_at: '2024-01-01T00:00:00',
        }),
      })
    }
    if (url === '/api/platforms') {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(config.platforms) })
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
  })
}

describe('TaskGeneratorsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.token = adminToken
    toastMock.success.mockClear()
    toastMock.error.mockClear()
  })

  it('renders email trigger card', async () => {
    vi.stubGlobal('fetch', setupFetch())
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="email-trigger-card"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Email Trigger')
  })

  it('shows no-credentials warning when email not configured', async () => {
    vi.stubGlobal('fetch', setupFetch({ platforms: [{ id: 'email', status: 'disconnected' }] }))
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="email-no-credentials"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Email credentials are not configured')
  })

  it('shows form fields when email credentials exist', async () => {
    vi.stubGlobal('fetch', setupFetch())
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="email-profile-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-poll-interval"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-task-prompt"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-save"]').exists()).toBe(true)
  })

  it('populates profiles dropdown', async () => {
    vi.stubGlobal('fetch', setupFetch())
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const select = wrapper.find('[data-testid="email-profile-select"]')
    const options = select.findAll('option')
    // Default + Profile A + Profile B
    expect(options.length).toBe(3)
    expect(options[0].text()).toBe('Default')
    expect(options[1].text()).toBe('Profile A')
    expect(options[2].text()).toBe('Profile B')
  })

  it('populates form from existing generator', async () => {
    vi.stubGlobal('fetch', setupFetch({
      generatorStatus: 200,
      generatorData: {
        id: 'gen-1',
        type: 'email',
        enabled: true,
        profile_id: 'profile-1',
        config: { poll_interval: 120, task_prompt: 'Handle this' },
        created_at: '2024-01-01T00:00:00',
        updated_at: '2024-01-01T00:00:00',
      },
    }))
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const toggle = wrapper.find('[data-testid="email-enabled-toggle"] input')
    expect((toggle.element as HTMLInputElement).checked).toBe(true)

    const pollInput = wrapper.find('[data-testid="email-poll-interval"]')
    expect((pollInput.element as HTMLInputElement).value).toBe('120')

    const promptInput = wrapper.find('[data-testid="email-task-prompt"]')
    expect((promptInput.element as HTMLTextAreaElement).value).toBe('Handle this')
  })

  it('validates poll interval minimum', async () => {
    vi.stubGlobal('fetch', setupFetch())
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const pollInput = wrapper.find('[data-testid="email-poll-interval"]')
    await pollInput.setValue('30')
    await pollInput.trigger('input')

    expect(wrapper.find('[data-testid="poll-interval-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Minimum poll interval is 60 seconds')
  })

  it('saves email generator on submit', async () => {
    const fetchMock = setupFetch()
    vi.stubGlobal('fetch', fetchMock)
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('[data-testid="email-save"]').trigger('click')
    await flushPromises()

    // Verify PUT was called
    const putCalls = fetchMock.mock.calls.filter(
      (call: any[]) => call[1]?.method === 'PUT'
    )
    expect(putCalls.length).toBe(1)
    expect(toastMock.success).toHaveBeenCalledWith('Email trigger settings saved.')
  })

  it('does not save when poll interval validation fails', async () => {
    const fetchMock = setupFetch()
    vi.stubGlobal('fetch', fetchMock)
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    // Set invalid poll interval
    await wrapper.find('[data-testid="email-poll-interval"]').setValue('10')

    await wrapper.find('[data-testid="email-save"]').trigger('click')
    await flushPromises()

    const putCalls = fetchMock.mock.calls.filter(
      (call: any[]) => call[1]?.method === 'PUT'
    )
    expect(putCalls.length).toBe(0)
  })

  it('disables toggle when email credentials not configured', async () => {
    vi.stubGlobal('fetch', setupFetch({ platforms: [{ id: 'email', status: 'disconnected' }] }))
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const toggle = wrapper.find('[data-testid="email-enabled-toggle"] input')
    expect((toggle.element as HTMLInputElement).disabled).toBe(true)
  })
})
