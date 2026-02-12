import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import App from '../../App.vue'

// Mock KanbanBoard to avoid task store / WebSocket setup
vi.mock('../KanbanBoard.vue', () => ({
  default: { template: '<div data-testid="kanban">Kanban</div>' },
}))

// Mock AccessDenied
vi.mock('../AccessDenied.vue', () => ({
  default: { template: '<div data-testid="access-denied">Access Denied</div>' },
}))

// Mock useApi to prevent real fetch
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
      { path: '/settings', component: { template: '<div>Settings</div>' } },
    ],
  })
}

describe('App header — admin dropdown', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('shows dropdown trigger for admin users', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'Admin User',
      resource_access: { 'content-manager': { roles: ['user', 'admin'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [router] },
    })

    // Admin should see their name as a clickable button with a chevron
    const trigger = wrapper.find('.dropdown-trigger button')
    expect(trigger.exists()).toBe(true)
    expect(trigger.text()).toContain('Admin User')
  })

  it('shows dropdown for non-admin users with Archived Tasks and Log out', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'Regular User',
      resource_access: { 'content-manager': { roles: ['user'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [router] },
    })

    // Non-admin should see dropdown trigger (all users with userDisplay get dropdown)
    const trigger = wrapper.find('.dropdown-trigger button')
    expect(trigger.exists()).toBe(true)
    expect(trigger.text()).toContain('Regular User')

    await trigger.trigger('click')

    const menuItems = wrapper.findAll('.dropdown-trigger .absolute button')
    expect(menuItems.length).toBe(2)
    expect(menuItems[0].text()).toBe('Archived Tasks')
    expect(menuItems[1].text()).toBe('Log out')
  })

  it('dropdown opens on click and shows Archived Tasks, Settings, and Log out for admin', async () => {
    const auth = useAuthStore()
    auth.setToken(fakeJwt({
      name: 'Admin User',
      resource_access: { 'content-manager': { roles: ['user', 'admin'] } },
    }))

    const router = makeRouter()
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [router] },
    })

    const trigger = wrapper.find('.dropdown-trigger button')
    await trigger.trigger('click')

    const menuItems = wrapper.findAll('.dropdown-trigger .absolute button')
    expect(menuItems.length).toBe(3)
    expect(menuItems[0].text()).toBe('Archived Tasks')
    expect(menuItems[1].text()).toBe('Settings')
    expect(menuItems[2].text()).toBe('Log out')
  })
})
