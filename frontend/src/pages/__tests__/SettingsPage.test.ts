import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import SettingsPage from '../SettingsPage.vue'
import AgentConfigurationPage from '../settings/AgentConfigurationPage.vue'
import TaskManagementPage from '../settings/TaskManagementPage.vue'
import SecurityPage from '../settings/SecurityPage.vue'
import IntegrationsPage from '../settings/IntegrationsPage.vue'
import UserManagementPage from '../settings/UserManagementPage.vue'

// Mock vue-sonner
const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

// Mock useApi functions that remaining self-loading sub-pages may touch. The LLM
// provider/model + platform logic now lives in @errand-ai/ui-components cards
// (stubbed below), so those helpers are just no-op safety nets.
vi.mock('../../composables/useApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../composables/useApi')>()
  return {
    ...actual,
    fetchProviders: vi.fn().mockResolvedValue([]),
    fetchProviderModels: vi.fn().mockResolvedValue([]),
    saveLlmModelsAndTimeouts: vi.fn().mockResolvedValue({}),
    fetchPlatforms: vi.fn().mockResolvedValue([]),
    savePlatformCredentials: vi.fn().mockResolvedValue({ status: 'connected' }),
    deletePlatformCredentials: vi.fn().mockResolvedValue(undefined),
    verifyPlatformCredentials: vi.fn().mockResolvedValue({ status: 'connected', last_verified_at: null }),
  }
})

// Mock shared library settings cards + shell (their behavior is covered by the
// library's own tests). The shell stub renders section labels, the error prop,
// and the default slot so child pages still mount.
vi.mock('@errand-ai/ui-components', () => ({
  SettingsShell: {
    name: 'SettingsShell',
    props: ['sections', 'loading', 'error'],
    emits: ['section-change'],
    template: `
      <div data-testid="settings-shell">
        <div v-if="error" data-testid="settings-error">{{ error }}</div>
        <nav data-testid="settings-sidebar">
          <a v-for="s in sections" :key="s.id">{{ s.label }}</a>
        </nav>
        <slot />
      </div>
    `,
  },
  SystemPromptCard: { name: 'SystemPromptCard', template: '<div data-testid="system-prompt-card">System Prompt</div>' },
  SkillsRepoCard: { name: 'SkillsRepoCard', template: '<div data-testid="skills-repo-card">Skills Repository</div>' },
  McpServersCard: { name: 'McpServersCard', template: '<div data-testid="mcp-servers-card">MCP Servers</div>' },
  LitellmMcpCard: { name: 'LitellmMcpCard', template: '<div data-testid="litellm-mcp-card">LiteLLM</div>' },
  TaskManagementCard: { name: 'TaskManagementCard', template: '<div data-testid="task-management-card">Task Management</div>' },
  TelemetryCard: { name: 'TelemetryCard', template: '<div data-testid="telemetry-card">Telemetry</div>' },
  CloudStorageCard: { name: 'CloudStorageCard', template: '<div data-testid="cloud-storage-card">Cloud storage</div>' },
  JiraCredentialCard: { name: 'JiraCredentialCard', template: '<div data-testid="jira-credential-card">Jira</div>' },
  // Wave 2 cards (their behavior is covered by the library's own tests).
  LlmProviderCard: { name: 'LlmProviderCard', template: '<div data-testid="llm-provider-card">LLM Providers</div>' },
  LlmModelCard: { name: 'LlmModelCard', template: '<div data-testid="llm-model-card">LLM Models</div>' },
  GoogleWorkspaceCard: { name: 'GoogleWorkspaceCard', template: '<div data-testid="google-workspace-card">Google Workspace</div>' },
  PlatformsCard: { name: 'PlatformsCard', template: '<div data-testid="platforms-card">Platforms</div>' },
}))

import { fetchProviders, fetchProviderModels, saveLlmModelsAndTimeouts } from '../../composables/useApi'

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const adminToken = fakeJwt({
  name: 'Admin',
  resource_access: { 'errand': { roles: ['admin'] } },
})

function mockSettingsAndSkills(
  settingsData: Record<string, unknown> = {},
  skillsData: unknown[] = [],
) {
  return vi.fn().mockImplementation((url: string) => {
    if (url === '/api/skills') {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(skillsData) })
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(settingsData) })
  })
}

function makeSettingsRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/settings',
        component: SettingsPage,
        children: [
          { path: '', redirect: { name: 'settings-agent' } },
          { path: 'agent', name: 'settings-agent', component: AgentConfigurationPage },
          { path: 'tasks', name: 'settings-tasks', component: TaskManagementPage },
          { path: 'security', name: 'settings-security', component: SecurityPage },
          { path: 'profiles', name: 'settings-profiles', component: { template: '<div>Task Profiles</div>' } },
          { path: 'integrations', name: 'settings-integrations', component: IntegrationsPage },
          { path: 'users', name: 'settings-users', component: UserManagementPage },
        ],
      },
    ],
  })
}

async function mountSettings(route = '/settings/agent', options: { attachTo?: Element } = {}) {
  const router = makeSettingsRouter()
  await router.push(route)
  await router.isReady()

  const wrapper = mount(
    { template: '<router-view />' },
    {
      global: { plugins: [router] },
      ...options,
    },
  )
  await flushPromises()
  return { wrapper, router }
}

describe('SettingsPage', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.setToken(adminToken)
    fetchMock = mockSettingsAndSkills()
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(fetchProviders).mockResolvedValue([])
    vi.mocked(fetchProviderModels).mockResolvedValue([])
    vi.mocked(saveLlmModelsAndTimeouts).mockResolvedValue({})
    toastMock.success.mockClear()
    toastMock.error.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // --- Shell layout ---

  describe('Shell layout', () => {
    it('mounts SettingsShell with all nine section labels', async () => {
      const { wrapper } = await mountSettings()

      expect(wrapper.find('[data-testid="settings-shell"]').exists()).toBe(true)
      const links = wrapper.find('[data-testid="settings-sidebar"]').findAll('a')
      expect(links.map(l => l.text())).toEqual([
        'Agent Configuration',
        'Task Management',
        'Security',
        'Task Profiles',
        'Integrations',
        'Task Generators',
        'Cloud Service',
        'Shared Workspace',
        'User Management',
      ])
    })

    it('navigates when the shell emits section-change', async () => {
      const { wrapper, router } = await mountSettings('/settings/agent')

      const shell = wrapper.findComponent({ name: 'SettingsShell' })
      shell.vm.$emit('section-change', 'tasks')
      await flushPromises()

      expect(router.currentRoute.value.name).toBe('settings-tasks')
    })

    // Post-Wave-2: the Settings page is a pure navigation shell — it no longer
    // loads /api/settings, so there is no page-level access-denied or network
    // error state. Each self-loading card surfaces its own errors (covered by
    // the library's tests and the individual component tests).
  })

  // --- Sub-page: Agent Configuration ---

  describe('Agent Configuration sub-page', () => {
    // --- Skills ---

    it('shows Skills section with skill list', async () => {
      fetchMock = mockSettingsAndSkills({}, [
        { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [], created_at: '', updated_at: '' },
        { id: '2', name: 'coder', description: 'Code generation', instructions: 'Code text', files: [], created_at: '', updated_at: '' },
      ])
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.text()).toContain('Skills')
      expect(wrapper.text()).toContain('(2)')
      expect(wrapper.text()).toContain('researcher')
      expect(wrapper.text()).toContain('Web research')
      expect(wrapper.text()).toContain('coder')
      expect(wrapper.text()).toContain('Code generation')
    })

    it('shows empty state when no skills defined', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.text()).toContain('No skills defined yet')
      expect(wrapper.text()).toContain('Add Skill')
    })

    it('creates a new skill via POST /api/skills', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
        if (url === '/api/skills' && _opts?.method === 'POST') {
          return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: 'new-id', name: 'researcher', description: 'Web research', instructions: 'You are a researcher.', files: [] }) })
        }
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      const addBtn = wrapper.find('[data-testid="skill-add"]')
      await addBtn.trigger('click')

      await wrapper.find('[data-testid="skill-name-input"]').setValue('researcher')
      await wrapper.find('[data-testid="skill-description-input"]').setValue('Web research')
      await wrapper.find('[data-testid="skill-instructions-input"]').setValue('You are a researcher.')
      await wrapper.find('[data-testid="skill-save"]').trigger('click')
      await flushPromises()

      const postCall = fetchMock.mock.calls.find(
        (call: any[]) => call[0] === '/api/skills' && call[1]?.method === 'POST'
      )
      expect(postCall).toBeTruthy()
      const body = JSON.parse(postCall![1].body as string)
      expect(body.name).toBe('researcher')
      expect(toastMock.success).toHaveBeenCalledWith('Skill saved.')
    })

    it('deletes a skill via confirmation dialog', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
        if (url === '/api/skills/1' && _opts?.method === 'DELETE') {
          return Promise.resolve({ ok: true, status: 204 })
        }
        if (url === '/api/skills') {
          return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([
            { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [], created_at: '', updated_at: '' },
          ]) })
        }
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent', { attachTo: document.body })

      const deleteBtn = wrapper.find('[data-testid="skill-delete"]')
      await deleteBtn.trigger('click')
      await flushPromises()

      const confirmBtn = wrapper.find('[data-testid="skill-delete-confirm"]')
      expect(confirmBtn.exists()).toBe(true)
      await confirmBtn.trigger('click')
      await flushPromises()

      const deleteCall = fetchMock.mock.calls.find(
        (call: any[]) => call[0] === '/api/skills/1' && call[1]?.method === 'DELETE'
      )
      expect(deleteCall).toBeTruthy()
      expect(toastMock.success).toHaveBeenCalledWith('Skill deleted.')

      wrapper.unmount()
    })

    it('cancels skill deletion via confirmation dialog', async () => {
      fetchMock = mockSettingsAndSkills({}, [
        { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [], created_at: '', updated_at: '' },
      ])
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent', { attachTo: document.body })

      const deleteBtn = wrapper.find('[data-testid="skill-delete"]')
      await deleteBtn.trigger('click')
      await flushPromises()

      const cancelBtn = wrapper.find('[data-testid="skill-delete-cancel"]')
      expect(cancelBtn.exists()).toBe(true)
      await cancelBtn.trigger('click')
      await flushPromises()

      const deleteCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'DELETE'
      )
      expect(deleteCall).toBeUndefined()

      wrapper.unmount()
    })

    it('shows name validation error for invalid name in real-time', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const addBtn = wrapper.find('[data-testid="skill-add"]')
      await addBtn.trigger('click')

      const nameInput = wrapper.find('[data-testid="skill-name-input"]')
      await nameInput.setValue('Invalid Name')
      await nameInput.trigger('input')
      await flushPromises()

      expect(wrapper.text()).toContain('Name must be lowercase')
    })

    it('shows description character counter', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const addBtn = wrapper.find('[data-testid="skill-add"]')
      await addBtn.trigger('click')

      const charCount = wrapper.find('[data-testid="description-char-count"]')
      expect(charCount.text()).toBe('0/1024')

      await wrapper.find('[data-testid="skill-description-input"]').setValue('Hello world')
      await flushPromises()

      expect(charCount.text()).toBe('11/1024')
    })

    it('opens edit form and submits PUT for existing skill', async () => {
      fetchMock = mockSettingsAndSkills({}, [
        { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [], created_at: '', updated_at: '' },
      ])
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      await wrapper.find('[data-testid="skill-edit"]').trigger('click')
      await flushPromises()

      const nameInput = wrapper.find('[data-testid="skill-name-input"]')
      expect((nameInput.element as HTMLInputElement).value).toBe('researcher')

      fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
        if (url === '/api/skills/1' && _opts?.method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: '1', name: 'researcher-v2', description: 'Updated', instructions: 'New text' }) })
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: '1', name: 'researcher-v2', description: 'Updated', instructions: 'New text', files: [], created_at: '', updated_at: '' }]) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      await nameInput.setValue('researcher-v2')
      await wrapper.find('[data-testid="skill-description-input"]').setValue('Updated')
      await wrapper.find('[data-testid="skill-instructions-input"]').setValue('New text')
      await wrapper.find('[data-testid="skill-save"]').trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT' && call[0]?.includes('/api/skills/1')
      )
      expect(putCall).toBeTruthy()
      const body = JSON.parse(putCall![1].body as string)
      expect(body.name).toBe('researcher-v2')
      expect(toastMock.success).toHaveBeenCalledWith('Skill saved.')
    })

    it('shows file count per skill', async () => {
      fetchMock = mockSettingsAndSkills({}, [
        { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [
          { id: 'f1', path: 'scripts/extract.py', created_at: '' },
          { id: 'f2', path: 'references/guide.md', created_at: '' },
        ], created_at: '', updated_at: '' },
      ])
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.text()).toContain('2 file(s)')
    })

    it('toggles file panel on Files button click', async () => {
      fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/skills/1') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [{ id: 'f1', path: 'scripts/extract.py', content: '#!/bin/bash', created_at: '' }] }) })
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [{ id: 'f1', path: 'scripts/extract.py', created_at: '' }], created_at: '', updated_at: '' }]) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.find('[data-testid="skill-files-panel"]').exists()).toBe(false)

      const filesToggle = wrapper.find('[data-testid="skill-files-toggle"]')
      await filesToggle.trigger('click')
      await flushPromises()

      expect(wrapper.find('[data-testid="skill-files-panel"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('scripts/')
      expect(wrapper.text()).toContain('extract.py')
    })

  })

  // --- Sub-page: Task Management ---

  // --- Sub-page: Security ---

  describe('Security sub-page', () => {
    it('shows MCP API Key section with masked key when key exists', async () => {
      fetchMock = mockSettingsAndSkills({ mcp_api_key: 'abc123def456' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('MCP API Key')
      expect(wrapper.text()).toContain('API Key')
      const codeEl = wrapper.find('code')
      expect(codeEl.text()).toBe('\u2022'.repeat(32))
    })

    it('shows placeholder message when no API key exists', async () => {
      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('No API key generated')
    })

    it('surfaces a load error instead of the misleading empty state when settings fail to load', async () => {
      // Both server-admin cards self-load /api/settings; a 403/transient failure
      // must not render the "restart the backend to auto-generate" remediation.
      fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ detail: 'Admin role required' }) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.find('[data-testid="mcp-load-error"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="ssh-load-error"]').exists()).toBe(true)
      expect(wrapper.text()).not.toContain('No API key generated')
      expect(wrapper.text()).not.toContain('No SSH key generated')
    })

    it('reveals and hides API key on toggle', async () => {
      fetchMock = mockSettingsAndSkills({ mcp_api_key: 'secret-key-value' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const revealBtn = wrapper.find('[data-testid="mcp-key-reveal"]')
      const codeEl = wrapper.find('code')
      expect(revealBtn.text()).toBe('Reveal')
      expect(codeEl.text()).toBe('\u2022'.repeat(32))

      await revealBtn.trigger('click')
      expect(revealBtn.text()).toBe('Hide')
      expect(codeEl.text()).toBe('secret-key-value')

      await revealBtn.trigger('click')
      expect(revealBtn.text()).toBe('Reveal')
      expect(codeEl.text()).toBe('\u2022'.repeat(32))
    })

    it('copies API key to clipboard', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined)
      Object.assign(navigator, { clipboard: { writeText: writeTextMock } })

      fetchMock = mockSettingsAndSkills({ mcp_api_key: 'key-to-copy' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const copyBtn = wrapper.find('[data-testid="mcp-key-copy"]')
      expect(copyBtn.text()).toBe('Copy')

      await copyBtn.trigger('click')
      await flushPromises()

      expect(writeTextMock).toHaveBeenCalledWith('key-to-copy')
      expect(copyBtn.text()).toBe('Copied!')
    })

    it('regenerates API key on confirm via dialog', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        if (url === '/api/settings/regenerate-mcp-key') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ mcp_api_key: 'new-key-456' }) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ mcp_api_key: 'old-key-123' }) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security', { attachTo: document.body })

      const regenBtn = wrapper.find('[data-testid="mcp-key-regenerate"]')
      await regenBtn.trigger('click')
      await flushPromises()

      const confirmBtn = wrapper.find('[data-testid="mcp-regenerate-confirm"]')
      expect(confirmBtn.exists()).toBe(true)
      await confirmBtn.trigger('click')
      await flushPromises()

      const postCall = fetchMock.mock.calls.find(
        (call: any[]) => call[0] === '/api/settings/regenerate-mcp-key'
      )
      expect(postCall).toBeTruthy()
      expect(postCall![1].method).toBe('POST')

      const revealBtn = wrapper.find('[data-testid="mcp-key-reveal"]')
      await revealBtn.trigger('click')
      expect(wrapper.text()).toContain('new-key-456')
      expect(toastMock.success).toHaveBeenCalledWith('API key regenerated.')

      wrapper.unmount()
    })

    it('does not regenerate when dialog is cancelled', async () => {
      fetchMock = mockSettingsAndSkills({ mcp_api_key: 'old-key-123' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security', { attachTo: document.body })

      const regenBtn = wrapper.find('[data-testid="mcp-key-regenerate"]')
      await regenBtn.trigger('click')
      await flushPromises()

      const cancelBtn = wrapper.find('[data-testid="mcp-regenerate-cancel"]')
      expect(cancelBtn.exists()).toBe(true)
      await cancelBtn.trigger('click')
      await flushPromises()

      // Only the initial GET call (settings) — no regenerate call made
      const regenCall = fetchMock.mock.calls.find(
        (call: any[]) => call[0] === '/api/settings/regenerate-mcp-key'
      )
      expect(regenCall).toBeUndefined()

      wrapper.unmount()
    })

    it('renders example MCP configuration with masked key', async () => {
      fetchMock = mockSettingsAndSkills({ mcp_api_key: 'test-api-key' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('Example MCP Configuration')
      expect(wrapper.text()).toContain('errand')
      expect(wrapper.text()).toContain('/mcp')
      expect(wrapper.text()).toContain('Bearer ' + '*'.repeat(32))
      expect(wrapper.text()).not.toContain('Bearer test-api-key')
    })

    it('copies example config to clipboard', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined)
      Object.assign(navigator, { clipboard: { writeText: writeTextMock } })

      fetchMock = mockSettingsAndSkills({ mcp_api_key: 'cfg-key' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const copyConfigBtn = wrapper.find('[data-testid="mcp-config-copy"]')
      expect(copyConfigBtn.text()).toBe('Copy Configuration')

      await copyConfigBtn.trigger('click')
      await flushPromises()

      expect(writeTextMock).toHaveBeenCalled()
      const copiedText = writeTextMock.mock.calls[0][0]
      const parsed = JSON.parse(copiedText)
      expect(parsed.mcpServers['errand'].url).toContain('/mcp')
      expect(parsed.mcpServers['errand'].headers.Authorization).toBe('Bearer cfg-key')
      expect(copyConfigBtn.text()).toBe('Copied!')
    })

    // --- Git SSH Key ---

    it('shows SSH public key when key exists', async () => {
      fetchMock = mockSettingsAndSkills({ ssh_public_key: 'ssh-ed25519 AAAA errand' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('Git SSH Key')
      const keyEl = wrapper.find('[data-testid="ssh-public-key"]')
      expect(keyEl.exists()).toBe(true)
      expect(keyEl.text()).toBe('ssh-ed25519 AAAA errand')
    })

    it('shows no-key message when SSH key is absent', async () => {
      const { wrapper } = await mountSettings('/settings/security')

      const noKey = wrapper.find('[data-testid="ssh-no-key"]')
      expect(noKey.exists()).toBe(true)
      expect(noKey.text()).toContain('No SSH key generated')
    })

    it('copies SSH public key to clipboard', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined)
      Object.assign(navigator, { clipboard: { writeText: writeTextMock } })

      fetchMock = mockSettingsAndSkills({ ssh_public_key: 'ssh-ed25519 COPY errand' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const copyBtn = wrapper.find('[data-testid="ssh-key-copy"]')
      await copyBtn.trigger('click')
      await flushPromises()

      expect(writeTextMock).toHaveBeenCalledWith('ssh-ed25519 COPY errand')
      expect(copyBtn.text()).toBe('Copied!')
    })

    it('regenerates SSH key on confirm via dialog', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        if (url === '/api/settings/regenerate-ssh-key') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ssh_public_key: 'ssh-ed25519 NEW errand' }) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ssh_public_key: 'ssh-ed25519 OLD errand' }) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security', { attachTo: document.body })

      const regenBtn = wrapper.find('[data-testid="ssh-key-regenerate"]')
      await regenBtn.trigger('click')
      await flushPromises()

      const confirmBtn = wrapper.find('[data-testid="ssh-regenerate-confirm"]')
      expect(confirmBtn.exists()).toBe(true)
      await confirmBtn.trigger('click')
      await flushPromises()

      const postCall = fetchMock.mock.calls.find(
        (call: any[]) => call[0] === '/api/settings/regenerate-ssh-key'
      )
      expect(postCall).toBeTruthy()

      const keyEl = wrapper.find('[data-testid="ssh-public-key"]')
      expect(keyEl.text()).toBe('ssh-ed25519 NEW errand')
      expect(toastMock.success).toHaveBeenCalledWith('SSH key regenerated.')

      wrapper.unmount()
    })

    it('displays default SSH hosts from settings', async () => {
      fetchMock = mockSettingsAndSkills({
        ssh_public_key: 'ssh-ed25519 AAAA errand',
        git_ssh_hosts: ['github.com', 'bitbucket.org'],
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('github.com')
      expect(wrapper.text()).toContain('bitbucket.org')
    })

    it('adds a new SSH host', async () => {
      fetchMock = mockSettingsAndSkills({
        ssh_public_key: 'ssh-ed25519 AAAA errand',
        git_ssh_hosts: ['github.com'],
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const input = wrapper.find('[data-testid="ssh-host-input"]')
      await input.setValue('gitlab.com')
      const addBtn = wrapper.find('[data-testid="ssh-host-add"]')
      await addBtn.trigger('click')

      expect(wrapper.text()).toContain('gitlab.com')
      expect(wrapper.text()).toContain('github.com')
    })

    it('removes an SSH host', async () => {
      fetchMock = mockSettingsAndSkills({
        ssh_public_key: 'ssh-ed25519 AAAA errand',
        git_ssh_hosts: ['github.com', 'bitbucket.org'],
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const removeBtns = wrapper.findAll('[data-testid="ssh-host-remove"]')
      expect(removeBtns).toHaveLength(2)
      await removeBtns[0].trigger('click')

      expect(wrapper.text()).not.toContain('github.com')
      expect(wrapper.text()).toContain('bitbucket.org')
    })

    it('prevents adding a duplicate SSH host', async () => {
      fetchMock = mockSettingsAndSkills({
        ssh_public_key: 'ssh-ed25519 AAAA errand',
        git_ssh_hosts: ['github.com'],
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const input = wrapper.find('[data-testid="ssh-host-input"]')
      await input.setValue('github.com')
      const addBtn = wrapper.find('[data-testid="ssh-host-add"]')
      await addBtn.trigger('click')

      expect(wrapper.text()).toContain('already in the list')
    })

    it('saves SSH hosts on Save click', async () => {
      fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
          ssh_public_key: 'ssh-ed25519 AAAA errand',
          git_ssh_hosts: ['github.com', 'bitbucket.org'],
        }) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      const saveBtn = wrapper.find('[data-testid="ssh-hosts-save"]')
      await saveBtn.trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT' && call[1]?.body?.includes('git_ssh_hosts')
      )
      expect(putCall).toBeTruthy()
      expect(toastMock.success).toHaveBeenCalledWith('SSH hosts saved.')
    })

    it('shows deploy key help text', async () => {
      fetchMock = mockSettingsAndSkills({ ssh_public_key: 'ssh-ed25519 AAAA errand' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('deploy key')
      expect(wrapper.text()).toContain('write access')
    })
  })

  // --- Sub-page rendering ---

  describe('Sub-page rendering', () => {
    it('Agent Configuration renders correct components', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.find('[data-testid="system-prompt-card"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('Skills')
      expect(wrapper.find('[data-testid="skills-repo-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="mcp-servers-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="litellm-mcp-card"]').exists()).toBe(true)
    })

    it('Task Management renders correct components', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      expect(wrapper.find('[data-testid="llm-provider-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="llm-model-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="task-management-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="telemetry-card"]').exists()).toBe(true)
    })

    it('Security renders correct components', async () => {
      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('Git SSH Key')
      expect(wrapper.text()).toContain('MCP API Key')
    })

    it('Integrations renders correct components', async () => {
      const { wrapper } = await mountSettings('/settings/integrations')

      expect(wrapper.find('[data-testid="google-workspace-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="cloud-storage-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="jira-credential-card"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="platforms-card"]').exists()).toBe(true)
    })
  })
})
