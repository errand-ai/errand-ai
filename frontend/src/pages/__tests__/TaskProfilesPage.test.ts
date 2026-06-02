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
    llm_timeout: null,
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
    llm_timeout: null,
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
    if (url === '/api/plugins' && (!opts || !opts.method || opts.method === 'GET')) {
      const data = responses['/api/plugins'] ?? []
      return { ok: true, status: 200, json: () => Promise.resolve(data) }
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

  it('shows "Plugins: N" summary on profile cards', async () => {
    const fetchFn = mockFetch({
      '/api/task-profiles': [
        { ...mockProfiles[0], enabled_plugins: ['pl-a', 'pl-b'] },
        { ...mockProfiles[1], enabled_plugins: null },
      ],
    })
    const { wrapper } = await mountPage(fetchFn)
    const cards = wrapper.findAll('[data-testid="profile-card"]')
    expect(cards[0].text()).toContain('Plugins: 2')
    expect(cards[1].text()).toContain('Plugins: None')
  })

  it('plugin multi-select lists enabled plugins only and saves selection', async () => {
    const plugins = [
      {
        id: 'pl-a',
        plugin_name: 'slack-toolkit',
        marketplace_id: 'mp-1',
        marketplace_name: 'acme',
        installed_version: '1.2.0',
        latest_available_version: '1.2.0',
        enabled: true,
        manifest: null,
        ignored_artifacts: null,
        skill_conflicts: null,
        update_available: false,
        skills: ['post-message'],
        mcp_servers: [{ raw: 'slack', namespaced: 'slack-toolkit__slack' }],
        installed_at: null,
        last_checked_at: null,
      },
      {
        id: 'pl-b',
        plugin_name: 'research-pack',
        marketplace_id: null,
        marketplace_name: null,
        installed_version: '0.1.0',
        latest_available_version: null,
        enabled: false,
        manifest: null,
        ignored_artifacts: null,
        skill_conflicts: null,
        update_available: false,
        skills: [],
        mcp_servers: [],
        installed_at: null,
        last_checked_at: null,
      },
    ]
    const fetchFn = mockFetch({ '/api/plugins': plugins })
    const { wrapper } = await mountPage(fetchFn)
    await wrapper.find('[data-testid="profile-add"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="profile-plugin-row-pl-a"]').exists()).toBe(true)
    // disabled plugin is excluded
    expect(wrapper.find('[data-testid="profile-plugin-row-pl-b"]').exists()).toBe(false)

    // Expand preview
    await wrapper.find('[data-testid="profile-plugin-row-pl-a"] button').trigger('click')
    expect(wrapper.find('[data-testid="profile-plugin-preview-pl-a"]').text()).toContain('post-message')
    expect(wrapper.find('[data-testid="profile-plugin-preview-pl-a"]').text()).toContain('slack-toolkit__slack')

    // Check the plugin and save
    await wrapper.find('[data-testid="profile-name-input"]').setValue('new-profile')
    await wrapper.find('[data-testid="profile-plugin-checkbox-pl-a"]').setValue(true)
    await wrapper.find('[data-testid="profile-save"]').trigger('click')
    await flushPromises()

    const postCalls = fetchFn.mock.calls.filter((call) => {
      const opts = call[1] as RequestInit | undefined
      return call[0] === '/api/task-profiles' && opts?.method === 'POST'
    })
    expect(postCalls).toHaveLength(1)
    const body = JSON.parse((postCalls[0][1] as RequestInit).body as string)
    expect(body.enabled_plugins).toEqual(['pl-a'])
  })

  it('shows stale plugin indicator for unknown enabled_plugins IDs and clears it', async () => {
    const plugins = [
      {
        id: 'pl-known',
        plugin_name: 'known',
        marketplace_id: null,
        marketplace_name: null,
        installed_version: '1.0.0',
        latest_available_version: null,
        enabled: true,
        manifest: null,
        ignored_artifacts: null,
        skill_conflicts: null,
        update_available: false,
        skills: [],
        mcp_servers: [],
        installed_at: null,
        last_checked_at: null,
      },
    ]
    const fetchFn = mockFetch({
      '/api/task-profiles': [{ ...mockProfiles[0], enabled_plugins: ['pl-known', 'pl-missing'] }],
      '/api/plugins': plugins,
    })
    const { wrapper } = await mountPage(fetchFn)
    await wrapper.findAll('[data-testid="profile-edit"]')[0].trigger('click')
    await flushPromises()
    const stale = wrapper.find('[data-testid="profile-plugin-stale-pl-missing"]')
    expect(stale.exists()).toBe(true)
    expect(stale.text()).toContain('Removed plugin')
    await wrapper.find('[data-testid="profile-plugin-stale-clear-pl-missing"]').trigger('click')
    expect(wrapper.find('[data-testid="profile-plugin-stale-pl-missing"]').exists()).toBe(false)
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
