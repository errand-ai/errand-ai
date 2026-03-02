import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useTaskStore } from '../../stores/tasks'
import { useAuthStore } from '../../stores/auth'
import App from '../../App.vue'

// Mock KanbanBoard to avoid heavy setup
vi.mock('../KanbanBoard.vue', () => ({
  default: { template: '<div data-testid="kanban">Kanban</div>' },
}))

// Mock AccessDenied
vi.mock('../AccessDenied.vue', () => ({
  default: { template: '<div data-testid="access-denied">Access Denied</div>' },
}))

// Mock useApi
vi.mock('../../composables/useApi', () => ({
  fetchTasks: vi.fn().mockResolvedValue([]),
  createTask: vi.fn(),
  updateTask: vi.fn(),
}))

// Mock useWebSocket
vi.mock('../../composables/useWebSocket', () => ({
  useWebSocket: () => ({
    status: { value: 'disconnected' },
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

// Mock vue-sonner
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
      { path: '/settings/cloud', component: { template: '<div>Cloud</div>' } },
    ],
  })
}

describe('Cloud indicator in header', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is hidden when cloud status is not_configured', async () => {
    // Stub fetch to return auth status + version + cloud not_configured
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/auth/status') return Promise.resolve({ ok: true, json: () => Promise.resolve({ mode: 'local' }) })
      if (url === '/api/version') return Promise.resolve({ ok: true, json: () => Promise.resolve({ current: '1.0.0' }) })
      if (url.includes('/api/cloud/status')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'not_configured' }) })
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))

    const auth = useAuthStore()
    auth.setToken(fakeJwt({ name: 'User', resource_access: { errand: { roles: ['admin'] } } }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-indicator"]').exists()).toBe(false)
  })

  it('shows green "Connected" when cloud status is connected', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/auth/status') return Promise.resolve({ ok: true, json: () => Promise.resolve({ mode: 'local' }) })
      if (url === '/api/version') return Promise.resolve({ ok: true, json: () => Promise.resolve({ current: '1.0.0' }) })
      if (url.includes('/api/cloud/status')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'connected' }) })
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))

    const auth = useAuthStore()
    auth.setToken(fakeJwt({ name: 'User', resource_access: { errand: { roles: ['admin'] } } }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    const indicator = wrapper.find('[data-testid="cloud-indicator"]')
    expect(indicator.exists()).toBe(true)
    expect(indicator.text()).toContain('Connected')
    expect(indicator.classes()).toContain('text-green-600')
  })

  it('shows red "Reconnect" when cloud status is error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/auth/status') return Promise.resolve({ ok: true, json: () => Promise.resolve({ mode: 'local' }) })
      if (url === '/api/version') return Promise.resolve({ ok: true, json: () => Promise.resolve({ current: '1.0.0' }) })
      if (url.includes('/api/cloud/status')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'error' }) })
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))

    const auth = useAuthStore()
    auth.setToken(fakeJwt({ name: 'User', resource_access: { errand: { roles: ['admin'] } } }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    const indicator = wrapper.find('[data-testid="cloud-indicator"]')
    expect(indicator.exists()).toBe(true)
    expect(indicator.text()).toContain('Reconnect')
    expect(indicator.classes()).toContain('text-red-500')
  })

  it('updates when cloud_status event changes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/auth/status') return Promise.resolve({ ok: true, json: () => Promise.resolve({ mode: 'local' }) })
      if (url === '/api/version') return Promise.resolve({ ok: true, json: () => Promise.resolve({ current: '1.0.0' }) })
      if (url.includes('/api/cloud/status')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'connected' }) })
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))

    const auth = useAuthStore()
    auth.setToken(fakeJwt({ name: 'User', resource_access: { errand: { roles: ['admin'] } } }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    // Verify initially connected
    expect(wrapper.find('[data-testid="cloud-indicator"]').text()).toContain('Connected')

    // Simulate cloud_status event changing to disconnected
    const taskStore = useTaskStore()
    taskStore.cloudStatus = 'disconnected'
    await flushPromises()

    const indicator = wrapper.find('[data-testid="cloud-indicator"]')
    expect(indicator.text()).toContain('Disconnected')
    expect(indicator.classes()).toContain('text-amber-500')
  })
})
