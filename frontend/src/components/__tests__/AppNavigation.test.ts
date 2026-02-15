import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import App from '../../App.vue'

// Mock child components
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
      { path: '/archived', component: { template: '<div>Archived</div>' } },
      { path: '/settings', component: { template: '<div>Settings</div>' } },
    ],
  })
}

describe('App navigation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders nav links for Board and Archived', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'User',
      resource_access: { 'content-manager': { roles: ['user'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    const nav = wrapper.find('[data-testid="main-nav"]')
    expect(nav.exists()).toBe(true)

    const links = nav.findAll('a')
    expect(links.length).toBe(2)
    expect(links[0].text()).toBe('Board')
    expect(links[1].text()).toBe('Archived')
  })

  it('shows Settings nav link for admin users', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'Admin',
      resource_access: { 'content-manager': { roles: ['user', 'admin'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    const nav = wrapper.find('[data-testid="main-nav"]')
    const links = nav.findAll('a')
    expect(links.length).toBe(3)
    expect(links[2].text()).toBe('Settings')
  })

  it('hides Settings nav link for non-admin users', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'User',
      resource_access: { 'content-manager': { roles: ['user'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    const nav = wrapper.find('[data-testid="main-nav"]')
    const links = nav.findAll('a')
    const settingsLink = links.find(l => l.text() === 'Settings')
    expect(settingsLink).toBeUndefined()
  })

  it('active route gets highlighted pill class', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'User',
      resource_access: { 'content-manager': { roles: ['user'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    const nav = wrapper.find('[data-testid="main-nav"]')
    const boardLink = nav.findAll('a')[0]
    expect(boardLink.classes()).toContain('bg-gray-100')
    expect(boardLink.classes()).toContain('text-gray-900')
  })

  it('dropdown only contains Log out', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'Admin',
      resource_access: { 'content-manager': { roles: ['user', 'admin'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    const trigger = wrapper.find('.dropdown-trigger button')
    await trigger.trigger('click')

    const menuItems = wrapper.findAll('.dropdown-trigger .absolute button')
    expect(menuItems.length).toBe(1)
    expect(menuItems[0].text()).toBe('Log out')
  })
})
