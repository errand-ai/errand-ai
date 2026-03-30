import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import WebhookTriggersSection from '../settings/WebhookTriggersSection.vue'

const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

const mockFetchTriggers = vi.fn().mockResolvedValue([])
const mockFetchProfiles = vi.fn().mockResolvedValue([
  { id: 'p1', name: 'Default Profile' },
])
const mockFetchJiraStatus = vi.fn().mockResolvedValue({ status: 'connected' })
const mockCreateTrigger = vi.fn().mockResolvedValue({ id: 't1', name: 'Test', source: 'jira' })
const mockUpdateTrigger = vi.fn().mockResolvedValue({})
const mockDeleteTrigger = vi.fn().mockResolvedValue(undefined)

vi.mock('../../composables/useApi', () => ({
  fetchWebhookTriggers: (...args: any[]) => mockFetchTriggers(...args),
  fetchTaskProfiles: (...args: any[]) => mockFetchProfiles(...args),
  fetchJiraCredentialStatus: (...args: any[]) => mockFetchJiraStatus(...args),
  createWebhookTrigger: (...args: any[]) => mockCreateTrigger(...args),
  updateWebhookTrigger: (...args: any[]) => mockUpdateTrigger(...args),
  deleteWebhookTrigger: (...args: any[]) => mockDeleteTrigger(...args),
}))

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/settings/integrations', component: { template: '<div />' } },
    ],
  })
}

async function mountComponent() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createTestRouter()
  router.push('/')
  await router.isReady()

  const wrapper = mount(WebhookTriggersSection, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return wrapper
}

describe('WebhookTriggersSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchTriggers.mockResolvedValue([])
    mockFetchJiraStatus.mockResolvedValue({ status: 'connected' })
  })

  it('renders empty state when no triggers', async () => {
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="no-triggers"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="add-trigger-btn"]').exists()).toBe(true)
  })

  it('shows jira warning when not connected', async () => {
    mockFetchJiraStatus.mockResolvedValue({ status: 'disconnected' })
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="jira-no-credentials"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="add-trigger-btn"]').attributes('disabled')).toBeDefined()
  })

  it('renders trigger list', async () => {
    mockFetchTriggers.mockResolvedValue([
      { id: 't1', name: 'Jira Bugs', source: 'jira', enabled: true, has_secret: true, filters: {}, actions: {}, profile_id: null, task_prompt: null },
      { id: 't2', name: 'Jira Tasks', source: 'jira', enabled: false, has_secret: false, filters: {}, actions: {}, profile_id: null, task_prompt: null },
    ])
    const wrapper = await mountComponent()
    const rows = wrapper.findAll('[data-testid="trigger-row"]')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('Jira Bugs')
    expect(rows[1].text()).toContain('Jira Tasks')
  })

  it('opens create form on button click', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
    expect(wrapper.find('[data-testid="trigger-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trigger-name"]').exists()).toBe(true)
  })

  it('validates name is required', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
    await wrapper.find('[data-testid="trigger-save-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="name-error"]').exists()).toBe(true)
    expect(mockCreateTrigger).not.toHaveBeenCalled()
  })

  it('creates trigger on save', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')

    await wrapper.find('[data-testid="trigger-name"]').setValue('Jira Bugs')
    await wrapper.find('[data-testid="trigger-save-btn"]').trigger('click')
    await flushPromises()

    expect(mockCreateTrigger).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Jira Bugs', source: 'jira' }),
    )
    expect(toastMock.success).toHaveBeenCalledWith('Trigger created')
  })

  it('generates a webhook secret', async () => {
    // Mock crypto.getRandomValues
    const mockValues = new Uint8Array(32).fill(0xab)
    vi.stubGlobal('crypto', { getRandomValues: (arr: Uint8Array) => { arr.set(mockValues); return arr } })

    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
    await wrapper.find('[data-testid="generate-secret-btn"]').trigger('click')

    const secretInput = wrapper.find('[data-testid="trigger-secret"]').element as HTMLInputElement
    expect(secretInput.value).toHaveLength(64) // 32 bytes hex
    expect(secretInput.value).toBe('ab'.repeat(32))

    vi.unstubAllGlobals()
  })

  it('shows delete confirmation modal', async () => {
    mockFetchTriggers.mockResolvedValue([
      { id: 't1', name: 'Deletable', source: 'jira', enabled: true, has_secret: false, filters: {}, actions: {}, profile_id: null, task_prompt: null },
    ])
    const wrapper = await mountComponent()

    // Click on trigger to open edit form
    await wrapper.find('[data-testid="trigger-row"]').trigger('click')
    await flushPromises()

    // Click delete
    await wrapper.find('[data-testid="trigger-delete-btn"]').trigger('click')
    expect(wrapper.find('[data-testid="delete-confirm-modal"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Deletable')
  })

  it('toggles trigger enabled state', async () => {
    mockFetchTriggers.mockResolvedValue([
      { id: 't1', name: 'Toggle Me', source: 'jira', enabled: true, has_secret: false, filters: {}, actions: {}, profile_id: null, task_prompt: null },
    ])
    const wrapper = await mountComponent()

    const toggle = wrapper.find('[data-testid="trigger-toggle-t1"]')
    await toggle.trigger('change')
    await flushPromises()

    expect(mockUpdateTrigger).toHaveBeenCalledWith('t1', { enabled: false })
  })
})
