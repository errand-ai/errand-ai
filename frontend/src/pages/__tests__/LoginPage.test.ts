import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent } from 'vue'
import { useAuthStore } from '../../stores/auth'
import LoginPage from '../LoginPage.vue'

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const DummyPage = defineComponent({ template: '<div>home</div>' })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: DummyPage },
      { path: '/login', name: 'login', component: LoginPage },
    ],
  })
}

describe('LoginPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.setAuthMode('local')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  async function mountLogin() {
    const router = makeRouter()
    await router.push('/login')
    await router.isReady()
    const wrapper = mount(LoginPage, { global: { plugins: [router] } })
    await flushPromises()
    return { wrapper, router }
  }

  it('renders login form', async () => {
    const { wrapper } = await mountLogin()

    expect(wrapper.find('[data-testid="login-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="login-username"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="login-password"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="login-submit"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Sign in to Errand')
  })

  it('submits form and sets token on success', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ access_token: token }),
    }))

    const { wrapper, router } = await mountLogin()

    await wrapper.find('[data-testid="login-username"]').setValue('admin')
    await wrapper.find('[data-testid="login-password"]').setValue('password123')
    await wrapper.find('[data-testid="login-form"]').trigger('submit')
    await flushPromises()

    const auth = useAuthStore()
    expect(auth.token).toBe(token)
    expect(router.currentRoute.value.path).toBe('/')
  })

  it('shows error on failed login', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Invalid credentials' }),
    }))

    const { wrapper } = await mountLogin()

    await wrapper.find('[data-testid="login-username"]').setValue('admin')
    await wrapper.find('[data-testid="login-password"]').setValue('wrong')
    await wrapper.find('[data-testid="login-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="login-error"]').text()).toBe('Invalid credentials')
  })

  it('shows generic error on network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))

    const { wrapper } = await mountLogin()

    await wrapper.find('[data-testid="login-username"]').setValue('admin')
    await wrapper.find('[data-testid="login-password"]').setValue('pass')
    await wrapper.find('[data-testid="login-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="login-error"]').text()).toBe('Unable to connect. Please try again.')
  })

  it('shows loading state during submission', async () => {
    let resolveLogin: (value: any) => void
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(r => { resolveLogin = r })))

    const { wrapper } = await mountLogin()

    await wrapper.find('[data-testid="login-username"]').setValue('admin')
    await wrapper.find('[data-testid="login-password"]').setValue('pass')
    await wrapper.find('[data-testid="login-form"]').trigger('submit')

    expect(wrapper.find('[data-testid="login-submit"]').text()).toBe('Signing in...')
    expect((wrapper.find('[data-testid="login-submit"]').element as HTMLButtonElement).disabled).toBe(true)

    resolveLogin!({ ok: true, json: () => Promise.resolve({ access_token: 'tok' }) })
    await flushPromises()
  })
})
