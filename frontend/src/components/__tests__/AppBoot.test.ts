import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent } from 'vue'
import { useAuthStore } from '../../stores/auth'
import App from '../../App.vue'

// Mock vue-sonner
vi.mock('vue-sonner', () => ({
  Toaster: defineComponent({ template: '<div />' }),
  toast: { success: vi.fn(), error: vi.fn() },
}))

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
      { path: '/login', name: 'login', component: DummyPage },
      { path: '/setup', name: 'setup', component: DummyPage },
      { path: '/archived', name: 'archived', component: DummyPage },
    ],
  })
}

describe('App boot sequence', () => {
  let locationHref: string

  beforeEach(() => {
    setActivePinia(createPinia())
    locationHref = ''
    // Mock window.location.href setter
    Object.defineProperty(window, 'location', {
      value: {
        ...window.location,
        hash: '',
        pathname: '/',
        get href() { return locationHref },
        set href(val: string) { locationHref = val },
      },
      writable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('routes to /setup when mode is setup', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ mode: 'setup' }),
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    mount(App, { global: { plugins: [router] } })
    await flushPromises()

    const auth = useAuthStore()
    expect(auth.authMode).toBe('setup')
    expect(router.currentRoute.value.name).toBe('setup')
  })

  it('routes to /login when mode is local and not authenticated', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ mode: 'local' }),
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    mount(App, { global: { plugins: [router] } })
    await flushPromises()

    const auth = useAuthStore()
    expect(auth.authMode).toBe('local')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('stays on home when mode is local and authenticated', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({ sub: 'admin', _roles: ['admin'] }))

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ mode: 'local' }),
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(auth.authMode).toBe('local')
    expect(router.currentRoute.value.name).toBe('home')
  })

  it('redirects to SSO login when mode is sso and not authenticated', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ mode: 'sso', login_url: '/auth/login' }),
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(locationHref).toBe('/auth/login')
  })

  it('handles auth status fetch failure gracefully', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(consoleSpy).toHaveBeenCalledWith('Failed to fetch auth status')
  })
})
