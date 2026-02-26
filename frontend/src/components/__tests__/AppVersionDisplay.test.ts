import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import App from '../../App.vue'

vi.mock('../KanbanBoard.vue', () => ({
  default: { template: '<div data-testid="kanban">Kanban</div>' },
}))

vi.mock('../AccessDenied.vue', () => ({
  default: { template: '<div data-testid="access-denied">Access Denied</div>' },
}))

vi.mock('../../composables/useApi', () => ({
  fetchTasks: vi.fn().mockResolvedValue([]),
  createTask: vi.fn(),
  updateTask: vi.fn(),
}))

vi.mock('../../composables/useWebSocket', () => ({
  useWebSocket: () => ({
    status: { value: 'disconnected' },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

vi.mock('vue-sonner', () => ({
  Toaster: { template: '<div data-testid="toaster" />' },
  toast: { success: vi.fn(), error: vi.fn() },
}))

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div>Home</div>' } },
    ],
  })
}

function stubFetch(versionResponse: { ok: boolean; json?: () => Promise<unknown> }) {
  let callCount = 0
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url === '/api/auth/status') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ mode: 'local' }) })
    }
    if (url === '/api/version') {
      return Promise.resolve(versionResponse)
    }
    return Promise.resolve({ ok: false })
  }))
}

async function mountApp() {
  const auth = useAuthStore()
  auth.setToken(fakeJwt({
    name: 'Test User',
    resource_access: { 'errand': { roles: ['user'] } },
  }))

  const router = makeRouter()
  await router.push('/')
  await router.isReady()

  const wrapper = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('App version display', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders semver version with v prefix', async () => {
    stubFetch({
      ok: true,
      json: () => Promise.resolve({ current: '0.65.0', latest: '0.65.0', update_available: false }),
    })

    const wrapper = await mountApp()
    const version = wrapper.find('[data-testid="version-display"]')
    expect(version.exists()).toBe(true)
    expect(version.text()).toBe('v0.65.0')
  })

  it('renders dev without v prefix', async () => {
    stubFetch({
      ok: true,
      json: () => Promise.resolve({ current: 'dev', latest: null, update_available: false }),
    })

    const wrapper = await mountApp()
    const version = wrapper.find('[data-testid="version-display"]')
    expect(version.exists()).toBe(true)
    expect(version.text()).toBe('dev')
  })

  it('shows update indicator when update is available', async () => {
    stubFetch({
      ok: true,
      json: () => Promise.resolve({ current: '0.65.0', latest: '0.66.0', update_available: true }),
    })

    const wrapper = await mountApp()
    const dot = wrapper.find('[data-testid="update-indicator"]')
    expect(dot.exists()).toBe(true)
    expect(dot.attributes('title')).toBe('v0.66.0 available')
  })

  it('hides update indicator when no update', async () => {
    stubFetch({
      ok: true,
      json: () => Promise.resolve({ current: '0.65.0', latest: '0.65.0', update_available: false }),
    })

    const wrapper = await mountApp()
    const dot = wrapper.find('[data-testid="update-indicator"]')
    expect(dot.exists()).toBe(false)
  })

  it('hides version display when fetch fails', async () => {
    stubFetch({ ok: false })

    const wrapper = await mountApp()
    const version = wrapper.find('[data-testid="version-display"]')
    expect(version.exists()).toBe(false)
  })

  it('renders PR version with v prefix', async () => {
    stubFetch({
      ok: true,
      json: () => Promise.resolve({ current: '0.65.0-pr66', latest: '0.65.0', update_available: false }),
    })

    const wrapper = await mountApp()
    const version = wrapper.find('[data-testid="version-display"]')
    expect(version.exists()).toBe(true)
    expect(version.text()).toBe('v0.65.0-pr66')
  })
})
