/**
 * Integration test for the Task Profiles settings page.
 *
 * Post-Wave-2 the page renders a single `<TaskProfileListCard>` from
 * `@errand-ai/ui-components` (the list + add/edit modal are internal to the card).
 * Like SettingsCapabilityGating, this test uses the REAL library so the card's
 * own load/modal/save behaviour is exercised end-to-end against a stubbed API.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createErrandUI, createDirectApi, type ServerCapabilities } from '@errand-ai/ui-components'
import TaskProfilesPage from '../settings/TaskProfilesPage.vue'

vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const PROFILE = {
  id: 'p1',
  name: 'Email triage',
  description: 'Handle email tasks',
  match_rules: null,
  model: null,
  system_prompt: null,
  max_turns: null,
  reasoning_effort: null,
  llm_timeout: null,
  mcp_servers: null,
  litellm_mcp_servers: null,
  skill_ids: null,
  include_git_skills: true,
  enabled_plugins: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

interface FetchCall {
  method: string
  url: string
  body: string | null
}

/** Stub fetch: GET /api/task-profiles returns [PROFILE]; other verbs echo ok. */
function stubApi(calls: FetchCall[]) {
  return vi.fn().mockImplementation((url: string, opts: RequestInit = {}) => {
    const method = opts.method ?? 'GET'
    calls.push({ method, url, body: (opts.body as string) ?? null })
    let body: unknown = {}
    if (url.endsWith('/api/task-profiles') && method === 'GET') body = [PROFILE]
    if (method === 'PUT' || method === 'POST') body = PROFILE
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
  })
}

function mountPage() {
  const caps = ref<ServerCapabilities>({ version: 't', capabilities: ['task_profiles'], connected: true })
  const api = createDirectApi({
    baseUrl: '/api',
    getToken: () => null,
    onUnauthorized: () => {},
    onForbidden: () => {},
    refreshToken: async () => false,
  })
  const errandUI = createErrandUI({ api, capabilities: caps })
  return mount(TaskProfilesPage, {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- duplicate Vue type trees under npm workspaces
    global: { plugins: [{ install: (a: any) => errandUI.install(a) }] },
  })
}

describe('TaskProfilesPage', () => {
  let calls: FetchCall[]

  beforeEach(() => {
    calls = []
    vi.stubGlobal('fetch', stubApi(calls))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the TaskProfileListCard with profiles loaded from the API', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[data-testid="task-profile-list"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Email triage')
    expect(calls.some((c) => c.method === 'GET' && c.url.endsWith('/api/task-profiles'))).toBe(true)
  })

  it('opens the internal edit modal and saves via PUT (modal is inside the card)', async () => {
    const wrapper = mountPage()
    await flushPromises()

    // Modal is not present until Edit is clicked.
    expect(wrapper.find('[data-testid="task-profile-modal"]').exists()).toBe(false)

    await wrapper.find('[data-testid="task-profile-edit-p1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="task-profile-modal"]').exists()).toBe(true)

    await wrapper.find('[data-testid="task-profile-name"]').setValue('Renamed profile')
    await wrapper.find('[data-testid="task-profile-submit"]').trigger('click')
    await flushPromises()

    const put = calls.find((c) => c.method === 'PUT' && c.url.endsWith('/api/task-profiles/p1'))
    expect(put).toBeTruthy()
    expect(JSON.parse(put!.body as string)).toMatchObject({ name: 'Renamed profile' })
    // Modal closes and the list reloads after a successful save.
    expect(wrapper.find('[data-testid="task-profile-modal"]').exists()).toBe(false)
  })

  it('opens the create modal from the "New profile" button', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.find('[data-testid="task-profile-create"]').trigger('click')
    await flushPromises()

    const modal = wrapper.find('[data-testid="task-profile-modal"]')
    expect(modal.exists()).toBe(true)
    const nameInput = wrapper.find('[data-testid="task-profile-name"]').element as HTMLInputElement
    expect(nameInput.value).toBe('')
  })
})
