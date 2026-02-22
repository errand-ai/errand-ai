import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import SettingsPage from '../SettingsPage.vue'
import UserManagementPage from '../settings/UserManagementPage.vue'

// Mock vue-sonner
const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

// Mock useApi
vi.mock('../../composables/useApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../composables/useApi')>()
  return {
    ...actual,
    fetchLlmModels: vi.fn().mockResolvedValue([]),
    saveLlmModel: vi.fn().mockResolvedValue({}),
    saveTaskProcessingModel: vi.fn().mockResolvedValue({}),
    fetchTranscriptionModels: vi.fn().mockResolvedValue([]),
    saveTranscriptionModel: vi.fn().mockResolvedValue({}),
    fetchPlatforms: vi.fn().mockResolvedValue([]),
    savePlatformCredentials: vi.fn().mockResolvedValue({ status: 'connected' }),
    deletePlatformCredentials: vi.fn().mockResolvedValue(undefined),
    verifyPlatformCredentials: vi.fn().mockResolvedValue({ status: 'connected', last_verified_at: null }),
  }
})

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const adminToken = fakeJwt({
  name: 'Admin',
  _roles: ['admin'],
})

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/settings',
        component: SettingsPage,
        children: [
          { path: 'users', name: 'settings-users', component: UserManagementPage },
        ],
      },
    ],
  })
}

describe('UserManagementPage', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.setToken(adminToken)
    auth.setAuthMode('local')
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      // Return metadata-enriched format
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          system_prompt: { value: '', source: 'default', sensitive: false, readonly: false },
          oidc_discovery_url: { value: '', source: 'default', sensitive: false, readonly: false },
          oidc_client_id: { value: '', source: 'default', sensitive: false, readonly: false },
          oidc_client_secret: { value: '', source: 'default', sensitive: true, readonly: false },
          oidc_roles_claim: { value: '', source: 'default', sensitive: false, readonly: false },
        }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    toastMock.success.mockClear()
    toastMock.error.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function mountUsers() {
    const router = makeRouter()
    await router.push('/settings/users')
    await router.isReady()
    const wrapper = mount(
      { template: '<router-view />' },
      { global: { plugins: [router] } },
    )
    await flushPromises()
    return { wrapper, router }
  }

  it('renders OIDC configuration section', async () => {
    const { wrapper } = await mountUsers()

    expect(wrapper.find('[data-testid="oidc-section"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Authentication Mode')
    expect(wrapper.find('[data-testid="oidc-discovery-url"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="oidc-client-id"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="oidc-client-secret"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="oidc-roles-claim"]').exists()).toBe(true)
  })

  it('renders Local Admin Account section', async () => {
    const { wrapper } = await mountUsers()

    expect(wrapper.find('[data-testid="local-admin-section"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Local Admin Account')
    expect(wrapper.find('[data-testid="admin-username"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="current-password"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="new-password"]').exists()).toBe(true)
  })

  it('shows lock icon for env-sourced OIDC fields', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          system_prompt: { value: '', source: 'default', sensitive: false, readonly: false },
          oidc_discovery_url: { value: 'https://auth.example.com/.well-known/openid-configuration', source: 'env', sensitive: false, readonly: true },
          oidc_client_id: { value: 'my-client', source: 'env', sensitive: false, readonly: true },
          oidc_client_secret: { value: 'sec****', source: 'env', sensitive: true, readonly: true },
          oidc_roles_claim: { value: '', source: 'default', sensitive: false, readonly: false },
        }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountUsers()

    const discoveryInput = wrapper.find('[data-testid="oidc-discovery-url"]')
    expect((discoveryInput.element as HTMLInputElement).disabled).toBe(true)

    const clientIdInput = wrapper.find('[data-testid="oidc-client-id"]')
    expect((clientIdInput.element as HTMLInputElement).disabled).toBe(true)
  })

  it('saves OIDC settings on Save & Enable SSO click', async () => {
    const { wrapper } = await mountUsers()

    await wrapper.find('[data-testid="oidc-discovery-url"]').setValue('https://auth.example.com/.well-known/openid-configuration')
    await wrapper.find('[data-testid="oidc-client-id"]').setValue('my-client')
    await wrapper.find('[data-testid="oidc-client-secret"]').setValue('my-secret')
    await wrapper.find('[data-testid="oidc-save"]').trigger('click')
    await flushPromises()

    const putCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'PUT'
    )
    expect(putCall).toBeTruthy()
    const body = JSON.parse(putCall![1].body as string)
    expect(body.oidc_discovery_url).toBe('https://auth.example.com/.well-known/openid-configuration')
    expect(body.oidc_client_id).toBe('my-client')
    expect(body.oidc_client_secret).toBe('my-secret')
    expect(toastMock.success).toHaveBeenCalledWith('SSO settings saved. Reload to use SSO login.')
  })

  it('calls change-password API on form submit', async () => {
    fetchMock = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      if (url === '/auth/local/change-password') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          system_prompt: { value: '', source: 'default', sensitive: false, readonly: false },
        }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountUsers()

    await wrapper.find('[data-testid="current-password"]').setValue('oldpass123')
    await wrapper.find('[data-testid="new-password"]').setValue('newpass456')
    await wrapper.find('[data-testid="confirm-new-password"]').setValue('newpass456')
    await wrapper.find('[data-testid="change-password-submit"]').trigger('click')
    await flushPromises()

    const postCall = fetchMock.mock.calls.find(
      (call: any[]) => call[0] === '/auth/local/change-password' && call[1]?.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall![1].body as string)
    expect(body.current_password).toBe('oldpass123')
    expect(body.new_password).toBe('newpass456')
    expect(toastMock.success).toHaveBeenCalledWith('Password changed successfully.')
  })

  it('shows password mismatch error', async () => {
    const { wrapper } = await mountUsers()

    await wrapper.find('[data-testid="current-password"]').setValue('oldpass123')
    await wrapper.find('[data-testid="new-password"]').setValue('newpass456')
    await wrapper.find('[data-testid="confirm-new-password"]').setValue('different')
    await wrapper.find('[data-testid="change-password-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="password-error"]').text()).toBe('Passwords do not match.')
  })

  it('shows short password error', async () => {
    const { wrapper } = await mountUsers()

    await wrapper.find('[data-testid="current-password"]').setValue('oldpass')
    await wrapper.find('[data-testid="new-password"]').setValue('short')
    await wrapper.find('[data-testid="confirm-new-password"]').setValue('short')
    await wrapper.find('[data-testid="change-password-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="password-error"]').text()).toBe('New password must be at least 8 characters.')
  })
})
