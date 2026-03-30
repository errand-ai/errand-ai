import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import JiraCredentialCard from '../settings/JiraCredentialCard.vue'

const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

const mockFetchStatus = vi.fn().mockResolvedValue({ platform_id: 'jira', status: 'disconnected', site_url: null, last_verified_at: null })
const mockSave = vi.fn().mockResolvedValue({ platform_id: 'jira', status: 'connected', display_name: 'Bot', site_url: 'https://acme.atlassian.net' })
const mockDelete = vi.fn().mockResolvedValue(undefined)

vi.mock('../../composables/useApi', () => ({
  fetchJiraCredentialStatus: (...args: any[]) => mockFetchStatus(...args),
  saveJiraCredentials: (...args: any[]) => mockSave(...args),
  deleteJiraCredentials: (...args: any[]) => mockDelete(...args),
}))

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
}

async function mountComponent() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createTestRouter()
  router.push('/')
  await router.isReady()

  const wrapper = mount(JiraCredentialCard, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return wrapper
}

describe('JiraCredentialCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchStatus.mockResolvedValue({ platform_id: 'jira', status: 'disconnected', site_url: null, last_verified_at: null })
  })

  it('renders disconnected state', async () => {
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="jira-status-badge"]').text()).toContain('Not Connected')
    expect(wrapper.find('[data-testid="jira-connect-btn"]').exists()).toBe(true)
  })

  it('renders connected state', async () => {
    mockFetchStatus.mockResolvedValue({
      platform_id: 'jira', status: 'connected', site_url: 'https://acme.atlassian.net', last_verified_at: '2026-03-01T00:00:00',
    })
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="jira-status-badge"]').text()).toContain('Connected')
    expect(wrapper.text()).toContain('acme.atlassian.net')
    expect(wrapper.find('[data-testid="jira-disconnect-btn"]').exists()).toBe(true)
  })

  it('shows form on connect button click', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="jira-connect-btn"]').trigger('click')
    expect(wrapper.find('[data-testid="jira-form"]').exists()).toBe(true)
  })

  it('validates all fields required', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="jira-connect-btn"]').trigger('click')
    await wrapper.find('[data-testid="jira-save-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="jira-form-error"]').text()).toContain('required')
    expect(mockSave).not.toHaveBeenCalled()
  })

  it('saves credentials', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="jira-connect-btn"]').trigger('click')

    await wrapper.find('[data-testid="jira-site-url"]').setValue('https://acme.atlassian.net')
    await wrapper.find('[data-testid="jira-cloud-id"]').setValue('abc-123')
    await wrapper.find('[data-testid="jira-api-token"]').setValue('tok_secret')
    await wrapper.find('[data-testid="jira-service-account"]').setValue('bot@acme.com')

    await wrapper.find('[data-testid="jira-save-btn"]').trigger('click')
    await flushPromises()

    expect(mockSave).toHaveBeenCalledWith({
      cloud_id: 'abc-123',
      api_token: 'tok_secret',
      site_url: 'https://acme.atlassian.net',
      service_account_email: 'bot@acme.com',
    })
    expect(toastMock.success).toHaveBeenCalled()
  })

  it('shows disconnect confirmation', async () => {
    mockFetchStatus.mockResolvedValue({
      platform_id: 'jira', status: 'connected', site_url: 'https://acme.atlassian.net', last_verified_at: null,
    })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="jira-disconnect-btn"]').trigger('click')
    expect(wrapper.find('[data-testid="jira-disconnect-modal"]').exists()).toBe(true)
  })

  it('disconnects on confirm', async () => {
    mockFetchStatus.mockResolvedValue({
      platform_id: 'jira', status: 'connected', site_url: 'https://acme.atlassian.net', last_verified_at: null,
    })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="jira-disconnect-btn"]').trigger('click')
    await wrapper.find('[data-testid="jira-disconnect-confirm-btn"]').trigger('click')
    await flushPromises()

    expect(mockDelete).toHaveBeenCalled()
    expect(toastMock.success).toHaveBeenCalledWith('Jira credentials removed')
  })
})
