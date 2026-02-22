import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent } from 'vue'
import { useAuthStore } from '../../stores/auth'
import SetupWizard from '../SetupWizard.vue'

// Mock vue-sonner
const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const DummyPage = defineComponent({ template: '<div>dummy</div>' })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: DummyPage },
      { path: '/setup', name: 'setup', component: SetupWizard },
      { path: '/settings', name: 'settings', component: DummyPage },
    ],
  })
}

describe('SetupWizard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.setAuthMode('setup')
    toastMock.success.mockClear()
    toastMock.error.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  async function mountSetup() {
    const router = makeRouter()
    await router.push('/setup')
    await router.isReady()
    const wrapper = mount(SetupWizard, { global: { plugins: [router] } })
    await flushPromises()
    return { wrapper, router }
  }

  it('renders step 1 initially', async () => {
    const { wrapper } = await mountSetup()

    expect(wrapper.find('[data-testid="setup-step1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Create Admin Account')
    expect(wrapper.find('[data-testid="setup-username"]').exists()).toBe(true)
  })

  it('shows step indicators', async () => {
    const { wrapper } = await mountSetup()

    const steps = wrapper.find('[data-testid="setup-steps"]')
    expect(steps.exists()).toBe(true)
  })

  it('shows password mismatch error', async () => {
    const { wrapper } = await mountSetup()

    await wrapper.find('[data-testid="setup-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('different')

    expect(wrapper.find('[data-testid="setup-password-mismatch"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-password-mismatch"]').text()).toBe('Passwords do not match.')
  })

  it('shows error for short password', async () => {
    vi.stubGlobal('fetch', vi.fn())

    const { wrapper } = await mountSetup()

    await wrapper.find('[data-testid="setup-username"]').setValue('admin')
    await wrapper.find('[data-testid="setup-password"]').setValue('short')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('short')
    await wrapper.find('[data-testid="setup-step1"]').find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step1-error"]').text()).toBe('Password must be at least 8 characters.')
  })

  it('advances to step 2 after creating admin', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      // /api/settings call from loadLlmMetadata
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    }))

    const { wrapper } = await mountSetup()

    await wrapper.find('[data-testid="setup-username"]').setValue('admin')
    await wrapper.find('[data-testid="setup-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-step1"]').find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step2"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('LLM Provider Configuration')
  })

  it('shows step 2 with test connection and continue buttons', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    }))

    const { wrapper } = await mountSetup()

    // Complete step 1
    await wrapper.find('[data-testid="setup-username"]').setValue('admin')
    await wrapper.find('[data-testid="setup-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-step1"]').find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-test-connection"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-continue-step2"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-provider-url"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-api-key"]').exists()).toBe(true)
  })

  it('handles create-user API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'User already exists' }),
    }))

    const { wrapper } = await mountSetup()

    await wrapper.find('[data-testid="setup-username"]').setValue('admin')
    await wrapper.find('[data-testid="setup-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-step1"]').find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step1-error"]').text()).toBe('User already exists')
  })
})
