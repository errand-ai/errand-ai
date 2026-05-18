import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import SettingsPage from '../../../pages/SettingsPage.vue'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/settings',
        component: SettingsPage,
        children: [
          { path: 'agent', name: 'settings-agent', component: { template: '<div>Agent</div>' } },
          { path: 'tasks', name: 'settings-tasks', component: { template: '<div>Tasks</div>' } },
        ],
      },
    ],
  })
}

describe('SettingsPage responsive layout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('mounts both the mobile picker and the desktop sidebar with responsive class gates', async () => {
    const router = makeRouter()
    await router.push('/settings/agent')
    await router.isReady()

    const wrapper = mount(SettingsPage, { global: { plugins: [router] } })
    await flushPromises()

    const picker = wrapper.find('[data-testid="settings-section-picker"]')
    expect(picker.exists()).toBe(true)
    expect(picker.classes()).toContain('sm:hidden')

    const sidebar = wrapper.find('[data-testid="settings-sidebar"]')
    expect(sidebar.exists()).toBe(true)
    expect(sidebar.classes()).toContain('hidden')
    expect(sidebar.classes()).toContain('sm:block')
  })

  it('picker reflects the active route label', async () => {
    const router = makeRouter()
    await router.push('/settings/tasks')
    await router.isReady()

    const wrapper = mount(SettingsPage, { global: { plugins: [router] } })
    await flushPromises()

    const button = wrapper.find('[data-testid="settings-section-picker-button"]')
    expect(button.text()).toContain('Task Management')
  })
})
