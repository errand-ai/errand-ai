import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import TaskProfilesPage from '../settings/TaskProfilesPage.vue'

const mockProfiles = [
  {
    id: 'p1',
    name: 'email-triage',
    description: 'Handle email tasks',
    match_rules: 'Tasks about email',
    model: { provider_id: 'prov1', model: 'claude-haiku-4-5-20251001' },
    system_prompt: null,
    max_turns: null,
    reasoning_effort: 'low',
    mcp_servers: null,
    litellm_mcp_servers: null,
    skill_ids: null,
    include_git_skills: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'p2',
    name: 'code-review',
    description: 'Code review tasks',
    match_rules: null,
    model: null,
    system_prompt: 'You are a code reviewer',
    max_turns: 5,
    reasoning_effort: null,
    mcp_servers: ['github'],
    litellm_mcp_servers: null,
    skill_ids: null,
    include_git_skills: true,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
]

function mockFetch(responses: Record<string, any> = {}) {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    if (url === '/api/task-profiles' && (!opts || !opts.method || opts.method === 'GET')) {
      const data = responses['/api/task-profiles'] ?? mockProfiles
      return { ok: true, status: 200, json: () => Promise.resolve(data) }
    }
    if (url === '/api/task-profiles' && opts?.method === 'POST') {
      const body = JSON.parse(opts.body as string)
      const newProfile = { id: 'p-new', ...body, created_at: '', updated_at: '' }
      return { ok: true, status: 201, json: () => Promise.resolve(newProfile) }
    }
    if (url?.startsWith('/api/task-profiles/') && opts?.method === 'PUT') {
      const body = JSON.parse(opts.body as string)
      return { ok: true, status: 200, json: () => Promise.resolve({ id: 'p1', name: 'email-triage', ...body, created_at: '', updated_at: '' }) }
    }
    if (url?.startsWith('/api/task-profiles/') && opts?.method === 'DELETE') {
      return { ok: true, status: 204 }
    }
    if (url === '/api/settings') {
      return { ok: true, status: 200, json: () => Promise.resolve({ task_processing_model: { value: { provider_id: null, model: 'claude-sonnet-4-5-20250929' }, source: 'default' } }) }
    }
    if (url === '/api/llm/providers') {
      return { ok: true, status: 200, json: () => Promise.resolve([{ id: 'prov1', name: 'Test Provider', base_url: 'https://api.test.com', api_key: 'sk-****', provider_type: 'openai_compatible', is_default: true, source: 'database', created_at: null, updated_at: null }]) }
    }
    if (url?.match(/\/api\/llm\/providers\/[^/]+\/models/)) {
      return { ok: true, status: 200, json: () => Promise.resolve(['claude-haiku-4-5-20251001', 'claude-sonnet-4-5-20250929']) }
    }
    if (url === '/api/worker/defaults') {
      return { ok: true, status: 200, json: () => Promise.resolve({ max_turns: '200', reasoning_effort: null }) }
    }
    if (url === '/api/litellm/mcp-servers') {
      return { ok: true, status: 200, json: () => Promise.resolve({ available: false, servers: {}, enabled: [] }) }
    }
    if (url === '/api/skills') {
      return { ok: true, status: 200, json: () => Promise.resolve([]) }
    }
    return { ok: true, status: 200, json: () => Promise.resolve({}) }
  })
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/settings/profiles', component: TaskProfilesPage },
    ],
  })
}

async function mountPage(fetchImpl?: ReturnType<typeof vi.fn>) {
  const fetchFn = fetchImpl ?? mockFetch()
  vi.stubGlobal('fetch', fetchFn)

  const pinia = createPinia()
  setActivePinia(pinia)

  const router = makeRouter()
  await router.push('/settings/profiles')
  await router.isReady()

  const wrapper = mount(TaskProfilesPage, {
    global: { plugins: [router, pinia] },
  })

  await flushPromises()
  return { wrapper, fetchFn }
}

describe('TaskProfilesPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders profile list', async () => {
    const { wrapper } = await mountPage()
    const cards = wrapper.findAll('[data-testid="profile-card"]')
    expect(cards).toHaveLength(2)
    expect(cards[0].text()).toContain('email-triage')
    expect(cards[1].text()).toContain('code-review')
  })

  it('shows empty state when no profiles exist', async () => {
    const { wrapper } = await mountPage(mockFetch({ '/api/task-profiles': [] }))
    const empty = wrapper.find('[data-testid="profiles-empty-state"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('No task profiles defined')
  })

  it('opens create form when Add Profile button is clicked', async () => {
    const { wrapper } = await mountPage()
    await wrapper.find('[data-testid="profile-add"]').trigger('click')
    const form = wrapper.find('[data-testid="profile-form"]')
    expect(form.exists()).toBe(true)
    expect(form.text()).toContain('New Profile')
  })

  it('opens create form from empty state button', async () => {
    const { wrapper } = await mountPage(mockFetch({ '/api/task-profiles': [] }))
    await wrapper.find('[data-testid="profile-add-empty"]').trigger('click')
    const form = wrapper.find('[data-testid="profile-form"]')
    expect(form.exists()).toBe(true)
  })

  it('opens edit form when Edit button is clicked', async () => {
    const { wrapper } = await mountPage()
    const editBtn = wrapper.findAll('[data-testid="profile-edit"]')[0]
    await editBtn.trigger('click')
    const form = wrapper.find('[data-testid="profile-form"]')
    expect(form.exists()).toBe(true)
    expect(form.text()).toContain('Edit Profile')
    const nameInput = wrapper.find('[data-testid="profile-name-input"]')
    expect((nameInput.element as HTMLInputElement).value).toBe('email-triage')
  })

  it('cancels form when Cancel is clicked', async () => {
    const { wrapper } = await mountPage()
    await wrapper.find('[data-testid="profile-add"]').trigger('click')
    expect(wrapper.find('[data-testid="profile-form"]').exists()).toBe(true)
    await wrapper.find('[data-testid="profile-cancel"]').trigger('click')
    expect(wrapper.find('[data-testid="profile-form"]').exists()).toBe(false)
  })

  it('shows error when creating with empty name', async () => {
    const { wrapper } = await mountPage()
    await wrapper.find('[data-testid="profile-add"]').trigger('click')
    await wrapper.find('[data-testid="profile-save"]').trigger('click')
    const error = wrapper.find('[data-testid="profiles-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('Name is required')
  })

  it('shows override summary on profile cards', async () => {
    const { wrapper } = await mountPage()
    const cards = wrapper.findAll('[data-testid="profile-card"]')
    // email-triage has model and reasoning
    expect(cards[0].text()).toContain('Model')
    expect(cards[0].text()).toContain('Reasoning')
    // code-review has prompt, max turns, and MCP
    expect(cards[1].text()).toContain('Prompt')
    expect(cards[1].text()).toContain('Max turns')
    expect(cards[1].text()).toContain('MCP')
  })

  it('shows delete confirmation dialog', async () => {
    const { wrapper } = await mountPage()
    const deleteBtn = wrapper.findAll('[data-testid="profile-delete"]')[0]
    await deleteBtn.trigger('click')
    await flushPromises()
    const cancelBtn = wrapper.find('[data-testid="profile-delete-cancel"]')
    expect(cancelBtn.exists()).toBe(true)
  })
})
