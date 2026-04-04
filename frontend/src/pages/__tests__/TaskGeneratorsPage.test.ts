import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import TaskGeneratorsPage from '../settings/TaskGeneratorsPage.vue'

// Mock vue-sonner
const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

// Mock useApi
vi.mock('../../composables/useApi', () => ({
  fetchTaskProfiles: vi.fn().mockResolvedValue([
    { id: 'profile-1', name: 'Profile A' },
    { id: 'profile-2', name: 'Profile B' },
  ]),
  fetchPlatforms: vi.fn().mockResolvedValue([
    { id: 'email', label: 'Email', status: 'connected' },
  ]),
  fetchEmailGenerator: vi.fn().mockResolvedValue(null),
  upsertEmailGenerator: vi.fn().mockResolvedValue({
    id: 'gen-1',
    type: 'email',
    enabled: false,
    profile_id: null,
    config: { poll_interval: 60 },
    created_at: '2024-01-01T00:00:00',
    updated_at: '2024-01-01T00:00:00',
  }),
  // Required by WebhookTriggersSection child component
  fetchWebhookTriggers: vi.fn().mockResolvedValue([]),
  createWebhookTrigger: vi.fn().mockResolvedValue({}),
  updateWebhookTrigger: vi.fn().mockResolvedValue({}),
  deleteWebhookTrigger: vi.fn().mockResolvedValue(undefined),
  fetchJiraCredentialStatus: vi.fn().mockResolvedValue({ status: 'disconnected' }),
}))

import {
  fetchTaskProfiles,
  fetchPlatforms,
  fetchEmailGenerator,
  upsertEmailGenerator,
} from '../../composables/useApi'

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const adminToken = fakeJwt({
  name: 'Admin',
  resource_access: { 'errand': { roles: ['admin'] } },
})

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/settings/task-generators', component: TaskGeneratorsPage },
      { path: '/settings/integrations', component: { template: '<div>Integrations</div>' } },
    ],
  })
}

describe('TaskGeneratorsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.token = adminToken
    toastMock.success.mockClear()
    toastMock.error.mockClear()
    vi.mocked(upsertEmailGenerator).mockClear()
    vi.mocked(fetchTaskProfiles).mockResolvedValue([
      { id: 'profile-1', name: 'Profile A', description: null, match_rules: null, model: null, system_prompt: null, max_turns: null, reasoning_effort: null, mcp_servers: null, litellm_mcp_servers: null, skill_ids: null, created_at: '', updated_at: '' },
      { id: 'profile-2', name: 'Profile B', description: null, match_rules: null, model: null, system_prompt: null, max_turns: null, reasoning_effort: null, mcp_servers: null, litellm_mcp_servers: null, skill_ids: null, created_at: '', updated_at: '' },
    ])
    vi.mocked(fetchPlatforms).mockResolvedValue([
      { id: 'email', label: 'Email', capabilities: ['email'], credential_schema: [], status: 'connected', last_verified_at: null },
    ])
    vi.mocked(fetchEmailGenerator).mockResolvedValue(null)
    vi.mocked(upsertEmailGenerator).mockResolvedValue({
      id: 'gen-1', type: 'email', enabled: false, profile_id: null,
      config: { poll_interval: 60 }, created_at: '2024-01-01T00:00:00', updated_at: '2024-01-01T00:00:00',
    })
  })

  it('renders email trigger card', async () => {
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="email-trigger-card"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Email Trigger')
  })

  it('shows no-credentials warning when email not configured', async () => {
    vi.mocked(fetchPlatforms).mockResolvedValue([
      { id: 'email', label: 'Email', capabilities: ['email'], credential_schema: [], status: 'disconnected', last_verified_at: null },
    ])
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="email-no-credentials"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Email credentials are not configured')
  })

  it('shows form fields when email credentials exist', async () => {
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="email-profile-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-poll-interval"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-task-prompt"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="email-save"]').exists()).toBe(true)
  })

  it('populates profiles dropdown', async () => {
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const select = wrapper.find('[data-testid="email-profile-select"]')
    const options = select.findAll('option')
    // Default + Profile A + Profile B
    expect(options.length).toBe(3)
    expect(options[0].text()).toBe('Default')
    expect(options[1].text()).toBe('Profile A')
    expect(options[2].text()).toBe('Profile B')
  })

  it('populates form from existing generator', async () => {
    vi.mocked(fetchEmailGenerator).mockResolvedValue({
      id: 'gen-1', type: 'email', enabled: true, profile_id: 'profile-1',
      config: { poll_interval: 120, task_prompt: 'Handle this' },
      created_at: '2024-01-01T00:00:00', updated_at: '2024-01-01T00:00:00',
    })
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const toggle = wrapper.find('[data-testid="email-enabled-toggle"] input')
    expect((toggle.element as HTMLInputElement).checked).toBe(true)

    const pollInput = wrapper.find('[data-testid="email-poll-interval"]')
    expect((pollInput.element as HTMLInputElement).value).toBe('120')

    const promptInput = wrapper.find('[data-testid="email-task-prompt"]')
    expect((promptInput.element as HTMLTextAreaElement).value).toBe('Handle this')
  })

  it('validates poll interval minimum', async () => {
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const pollInput = wrapper.find('[data-testid="email-poll-interval"]')
    await pollInput.setValue('30')
    await pollInput.trigger('input')

    expect(wrapper.find('[data-testid="poll-interval-error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Minimum poll interval is 60 seconds')
  })

  it('saves email generator on submit', async () => {
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('[data-testid="email-save"]').trigger('click')
    await flushPromises()

    expect(upsertEmailGenerator).toHaveBeenCalledOnce()
    expect(toastMock.success).toHaveBeenCalledWith('Email trigger settings saved.')
  })

  it('does not save when poll interval validation fails', async () => {
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    // Set invalid poll interval
    await wrapper.find('[data-testid="email-poll-interval"]').setValue('10')

    await wrapper.find('[data-testid="email-save"]').trigger('click')
    await flushPromises()

    expect(upsertEmailGenerator).not.toHaveBeenCalled()
  })

  it('disables toggle when email credentials not configured', async () => {
    vi.mocked(fetchPlatforms).mockResolvedValue([
      { id: 'email', label: 'Email', capabilities: ['email'], credential_schema: [], status: 'disconnected', last_verified_at: null },
    ])
    const router = createTestRouter()
    const wrapper = mount(TaskGeneratorsPage, { global: { plugins: [router] } })
    await flushPromises()

    const toggle = wrapper.find('[data-testid="email-enabled-toggle"] input')
    expect((toggle.element as HTMLInputElement).disabled).toBe(true)
  })
})
