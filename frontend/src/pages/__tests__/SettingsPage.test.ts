import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { nextTick } from 'vue'
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

// Mock the useApi functions used by LlmModelSettings and PlatformSettings
vi.mock('../../composables/useApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../composables/useApi')>()
  return {
    ...actual,
    fetchLlmModels: vi.fn().mockResolvedValue([]),
    saveLlmModel: vi.fn().mockResolvedValue({}),
    saveTaskProcessingModel: vi.fn().mockResolvedValue({}),
    fetchTranscriptionModels: vi.fn().mockResolvedValue([]),
    saveTranscriptionModel: vi.fn().mockResolvedValue({}),
    saveLlmTimeout: vi.fn().mockResolvedValue({}),
    fetchPlatforms: vi.fn().mockResolvedValue([]),
    savePlatformCredentials: vi.fn().mockResolvedValue({ status: 'connected' }),
    deletePlatformCredentials: vi.fn().mockResolvedValue(undefined),
    verifyPlatformCredentials: vi.fn().mockResolvedValue({ status: 'connected', last_verified_at: null }),
  }
})

import { fetchLlmModels, saveLlmModel, saveLlmTimeout, saveTaskProcessingModel, fetchTranscriptionModels, saveTranscriptionModel } from '../../composables/useApi'

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
    vi.mocked(fetchLlmModels).mockResolvedValue([])
    vi.mocked(saveLlmModel).mockResolvedValue({})
    vi.mocked(saveTaskProcessingModel).mockResolvedValue({})
    vi.mocked(fetchTranscriptionModels).mockResolvedValue([])
    vi.mocked(saveTranscriptionModel).mockResolvedValue({})
    toastMock.success.mockClear()
    toastMock.error.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // --- Layout and Navigation ---

  describe('Layout and navigation', () => {
    it('renders sidebar with all navigation items', async () => {
      const { wrapper } = await mountSettings()

      const sidebar = wrapper.find('[data-testid="settings-sidebar"]')
      expect(sidebar.exists()).toBe(true)

      const links = sidebar.findAll('a')
      expect(links).toHaveLength(5)
      expect(links[0].text()).toBe('Agent Configuration')
      expect(links[1].text()).toBe('Task Management')
      expect(links[2].text()).toBe('Security')
      expect(links[3].text()).toBe('Integrations')
      expect(links[4].text()).toBe('User Management')
    })

    it('highlights active sidebar link', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const sidebar = wrapper.find('[data-testid="settings-sidebar"]')
      const links = sidebar.findAll('a')
      expect(links[0].classes()).toContain('bg-gray-100')
      expect(links[0].classes()).toContain('text-gray-900')
      expect(links[1].classes()).toContain('text-gray-600')
    })

    it('highlights correct link when navigating to different sub-page', async () => {
      const { wrapper } = await mountSettings('/settings/security')

      const sidebar = wrapper.find('[data-testid="settings-sidebar"]')
      const links = sidebar.findAll('a')
      expect(links[2].classes()).toContain('bg-gray-100')
      expect(links[0].classes()).toContain('text-gray-600')
    })

    it('shows skeleton loading state before settings load', async () => {
      const router = makeSettingsRouter()
      await router.push('/settings/agent')
      await router.isReady()

      const wrapper = mount(
        { template: '<router-view />' },
        { global: { plugins: [router] } },
      )

      const skeleton = wrapper.find('[data-testid="settings-skeleton"]')
      expect(skeleton.exists()).toBe(true)
      expect(skeleton.findAll('.animate-pulse').length).toBeGreaterThanOrEqual(4)
    })

    it('shows access denied on 403', async () => {
      fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ detail: 'Admin role required' }) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings()

      expect(wrapper.text()).toContain('Access denied')
    })

    it('shows error on network failure', async () => {
      fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.reject(new Error('Network error'))
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings()

      expect(wrapper.text()).toContain('Failed to load settings')
    })
  })

  // --- Sub-page: Agent Configuration ---

  describe('Agent Configuration sub-page', () => {
    it('renders Agent Configuration sections after loading', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.text()).toContain('System Prompt')
      expect(wrapper.text()).toContain('Skills')
      expect(wrapper.text()).toContain('MCP Server Configuration')
    })

    it('loads existing system prompt into textarea', async () => {
      fetchMock = mockSettingsAndSkills({ system_prompt: 'Hello world' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      const textarea = wrapper.find('textarea')
      expect((textarea.element as HTMLTextAreaElement).value).toBe('Hello world')
    })

    it('saves system prompt on button click', async () => {
      let callCount = 0
      fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
        callCount++
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        if (_opts?.method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ system_prompt: 'new prompt' }) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      await wrapper.find('textarea').setValue('new prompt')
      const saveButtons = wrapper.findAll('button').filter(b => b.text() === 'Save')
      await saveButtons[0].trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT'
      )
      expect(putCall).toBeTruthy()
      expect(JSON.parse(putCall![1].body)).toEqual({ system_prompt: 'new prompt' })
      expect(toastMock.success).toHaveBeenCalledWith('System prompt saved.')
    })

    // --- MCP Server Configuration ---

    it('MCP section is collapsed by default', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const textareas = wrapper.findAll('textarea')
      expect(textareas.length).toBe(1)
      expect(wrapper.text()).toContain('MCP Server Configuration')
    })

    it('MCP section expands on click', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const buttons = wrapper.findAll('button')
      const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
      expect(mcpButton).toBeTruthy()
      await mcpButton!.trigger('click')

      const textareas = wrapper.findAll('textarea')
      expect(textareas.length).toBe(2)
    })

    it('loads MCP servers into text box when expanded', async () => {
      const mcpConfig = { servers: [{ name: 'test-server' }] }
      fetchMock = mockSettingsAndSkills({ mcp_servers: mcpConfig })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      const buttons = wrapper.findAll('button')
      const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
      await mcpButton!.trigger('click')

      const textareas = wrapper.findAll('textarea')
      const mcpTextarea = textareas[textareas.length - 1]
      expect((mcpTextarea.element as HTMLTextAreaElement).value).toContain('test-server')
    })

    it('shows JSON validation error for invalid JSON', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const buttons = wrapper.findAll('button')
      const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
      await mcpButton!.trigger('click')

      const textareas = wrapper.findAll('textarea')
      const mcpTextarea = textareas[textareas.length - 1]
      await mcpTextarea.setValue('not valid json {{{')

      const saveButtons = wrapper.findAll('button')
      const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
      await saveMcpButton!.trigger('click')
      await flushPromises()

      expect(wrapper.text()).toContain('Invalid JSON')
    })

    it('saves valid MCP JSON configuration', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      const buttons = wrapper.findAll('button')
      const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
      await mcpButton!.trigger('click')

      const textareas = wrapper.findAll('textarea')
      const mcpTextarea = textareas[textareas.length - 1]
      await mcpTextarea.setValue('{"mcpServers": {"test": {"url": "http://localhost:4000/mcp"}}}')

      const saveButtons = wrapper.findAll('button')
      const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
      await saveMcpButton!.trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT'
      )
      expect(putCall).toBeTruthy()
      expect(JSON.parse(putCall![1].body as string)).toEqual({
        mcp_servers: { mcpServers: { test: { url: 'http://localhost:4000/mcp' } } },
      })
      expect(toastMock.success).toHaveBeenCalledWith('MCP configuration saved.')
    })

    it('rejects STDIO MCP server configuration', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const buttons = wrapper.findAll('button')
      const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
      await mcpButton!.trigger('click')

      const textareas = wrapper.findAll('textarea')
      const mcpTextarea = textareas[textareas.length - 1]
      await mcpTextarea.setValue(JSON.stringify({
        mcpServers: { local: { command: 'npx', args: ['-y', 'some-mcp-server'] } },
      }))

      const saveButtons = wrapper.findAll('button')
      const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
      await saveMcpButton!.trigger('click')
      await flushPromises()

      expect(wrapper.text()).toContain('STDIO transport')
      expect(wrapper.text()).toContain("Server 'local'")
    })

    it('rejects MCP server entry missing url field', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      const buttons = wrapper.findAll('button')
      const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
      await mcpButton!.trigger('click')

      const textareas = wrapper.findAll('textarea')
      const mcpTextarea = textareas[textareas.length - 1]
      await mcpTextarea.setValue(JSON.stringify({
        mcpServers: { test: { headers: { key: 'value' } } },
      }))

      const saveButtons = wrapper.findAll('button')
      const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
      await saveMcpButton!.trigger('click')
      await flushPromises()

      expect(wrapper.text()).toContain("missing required 'url' field")
      expect(wrapper.text()).toContain("Server 'test'")
    })

    it('accepts valid HTTP Streaming MCP configuration', async () => {
      fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      const buttons = wrapper.findAll('button')
      const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
      await mcpButton!.trigger('click')

      const textareas = wrapper.findAll('textarea')
      const mcpTextarea = textareas[textareas.length - 1]
      await mcpTextarea.setValue(JSON.stringify({
        mcpServers: {
          argocd: {
            url: 'http://localhost:4000/argocd/mcp',
            headers: { 'x-litellm-api-key': 'Bearer sk-1234' },
          },
        },
      }))

      const saveButtons = wrapper.findAll('button')
      const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
      await saveMcpButton!.trigger('click')
      await flushPromises()

      expect(toastMock.success).toHaveBeenCalledWith('MCP configuration saved.')
    })

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

    // --- Skills Repository ---

    it('renders Skills Repository section', async () => {
      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.find('[data-testid="skills-repo-section"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('Skills Repository')
    })

    it('loads existing skills_git_repo config into form fields', async () => {
      fetchMock = mockSettingsAndSkills({
        skills_git_repo: {
          url: 'git@github.com:org/skills.git',
          branch: 'main',
          path: 'skills',
        },
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')
      await nextTick()

      const urlInput = wrapper.find('[data-testid="skills-repo-url"]').element as HTMLInputElement
      const branchInput = wrapper.find('[data-testid="skills-repo-branch"]').element as HTMLInputElement
      const pathInput = wrapper.find('[data-testid="skills-repo-path"]').element as HTMLInputElement
      expect(urlInput.value).toBe('git@github.com:org/skills.git')
      expect(branchInput.value).toBe('main')
      expect(pathInput.value).toBe('skills')
    })

    it('saves skills repo with all fields', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        if (opts?.method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      await wrapper.find('[data-testid="skills-repo-url"]').setValue('git@github.com:org/skills.git')
      await wrapper.find('[data-testid="skills-repo-branch"]').setValue('main')
      await wrapper.find('[data-testid="skills-repo-path"]').setValue('skills')
      await wrapper.find('[data-testid="skills-repo-save"]').trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT' && call[0] === '/api/settings'
      )
      expect(putCall).toBeTruthy()
      const body = JSON.parse(putCall![1].body as string)
      expect(body.skills_git_repo).toEqual({
        url: 'git@github.com:org/skills.git',
        branch: 'main',
        path: 'skills',
      })
      expect(toastMock.success).toHaveBeenCalledWith('Skills repository settings saved.')
    })

    it('saves skills repo with URL only (omits empty branch/path)', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        if (opts?.method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      await wrapper.find('[data-testid="skills-repo-url"]').setValue('git@github.com:org/skills.git')
      await wrapper.find('[data-testid="skills-repo-save"]').trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT' && call[0] === '/api/settings'
      )
      const body = JSON.parse(putCall![1].body as string)
      expect(body.skills_git_repo).toEqual({ url: 'git@github.com:org/skills.git' })
      expect(body.skills_git_repo.branch).toBeUndefined()
      expect(body.skills_git_repo.path).toBeUndefined()
    })

    it('clears skills repo config when URL is empty', async () => {
      fetchMock = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        if (opts?.method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ skills_git_repo: { url: 'git@github.com:org/skills.git' } }),
        })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')
      await nextTick()

      await wrapper.find('[data-testid="skills-repo-url"]').setValue('')
      await wrapper.find('[data-testid="skills-repo-save"]').trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT' && call[0] === '/api/settings'
      )
      const body = JSON.parse(putCall![1].body as string)
      expect(body.skills_git_repo).toBeNull()
    })

    // --- Unsaved changes ---

    it('shows unsaved changes indicator on system prompt modification', async () => {
      fetchMock = mockSettingsAndSkills({ system_prompt: 'original prompt' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/agent')

      expect(wrapper.text()).not.toContain('Unsaved changes')

      await wrapper.find('textarea').setValue('modified prompt')
      await nextTick()

      expect(wrapper.text()).toContain('Unsaved changes')
    })
  })

  // --- Sub-page: Task Management ---

  describe('Task Management sub-page', () => {
    it('renders LLM Models section with both dropdowns', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      expect(wrapper.text()).toContain('LLM Models')
      expect(wrapper.text()).toContain('Title Generation Model')
      expect(wrapper.text()).toContain('Default Model')
    })

    it('loads models from fetchLlmModels and populates dropdown', async () => {
      vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const options = wrapper.findAll('select option')
      const modelOptions = options.map((o) => o.text())
      expect(modelOptions).toContain('claude-haiku-4-5-20251001')
      expect(modelOptions).toContain('gpt-4o')
    })

    it('pre-selects current title generation model from settings', async () => {
      fetchMock = mockSettingsAndSkills({ llm_model: 'gpt-4o' })
      vi.stubGlobal('fetch', fetchMock)
      vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      expect((selects[0].element as HTMLSelectElement).value).toBe('gpt-4o')
    })

    it('saves title generation model on explicit Save click', async () => {
      vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      await selects[0].setValue('gpt-4o')

      const llmSection = wrapper.findAll('.shadow').find(el => el.text().includes('LLM Models'))
      const saveBtn = llmSection!.findAll('button').find(b => b.text() === 'Save')
      await saveBtn!.trigger('click')
      await flushPromises()

      expect(saveLlmModel).toHaveBeenCalledWith('gpt-4o')
      expect(toastMock.success).toHaveBeenCalledWith('Model settings saved.')
    })

    it('shows error when model list fails to load', async () => {
      vi.mocked(fetchLlmModels).mockRejectedValue(new Error('Failed'))

      const { wrapper } = await mountSettings('/settings/tasks')

      expect(wrapper.text()).toContain('Failed to load models')
    })

    it('defaults to claude-haiku when no llm_model in settings', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      expect((selects[0].element as HTMLSelectElement).value).toBe('claude-haiku-4-5-20251001')
    })

    // --- Task Processing Model ---

    it('loads task processing model from settings', async () => {
      fetchMock = mockSettingsAndSkills({ task_processing_model: 'gpt-4o' })
      vi.stubGlobal('fetch', fetchMock)
      vi.mocked(fetchLlmModels).mockResolvedValue(['claude-sonnet-4-5-20250929', 'gpt-4o'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      expect((selects[1].element as HTMLSelectElement).value).toBe('gpt-4o')
    })

    it('defaults task processing model to claude-sonnet when not in settings', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      expect((selects[1].element as HTMLSelectElement).value).toBe('claude-sonnet-4-5-20250929')
    })

    it('saves task processing model on Save click', async () => {
      vi.mocked(fetchLlmModels).mockResolvedValue(['claude-sonnet-4-5-20250929', 'gpt-4o'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      await selects[1].setValue('gpt-4o')

      const llmSection = wrapper.findAll('.shadow').find(el => el.text().includes('LLM Models'))
      const saveBtn = llmSection!.findAll('button').find(b => b.text() === 'Save')
      await saveBtn!.trigger('click')
      await flushPromises()

      expect(saveTaskProcessingModel).toHaveBeenCalledWith('gpt-4o')
    })

    it('disables both dropdowns when models endpoint fails', async () => {
      vi.mocked(fetchLlmModels).mockRejectedValue(new Error('Failed'))

      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      expect((selects[0].element as HTMLSelectElement).disabled).toBe(true)
      expect((selects[1].element as HTMLSelectElement).disabled).toBe(true)
    })

    // --- Transcription Model ---

    it('renders Transcription Model dropdown with filtered models', async () => {
      vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

      const { wrapper } = await mountSettings('/settings/tasks')

      expect(wrapper.text()).toContain('Transcription Model')
      const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
      expect(transcriptionSelect.exists()).toBe(true)

      const options = transcriptionSelect.findAll('option')
      const optionTexts = options.map(o => o.text())
      expect(optionTexts).toContain('whisper-1')
      expect(optionTexts).toContain('whisper-large-v3')
    })

    it('shows placeholder when no transcription model is selected', async () => {
      vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
      expect((transcriptionSelect.element as HTMLSelectElement).value).toBe('')
      expect(transcriptionSelect.text()).toContain('Select a model to enable voice input')
    })

    it('loads current transcription model from settings', async () => {
      fetchMock = mockSettingsAndSkills({ transcription_model: 'whisper-large-v3' })
      vi.stubGlobal('fetch', fetchMock)
      vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
      expect((transcriptionSelect.element as HTMLSelectElement).value).toBe('whisper-large-v3')
    })

    it('saves transcription model on Save click', async () => {
      vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
      await transcriptionSelect.setValue('whisper-1')

      const llmSection = wrapper.findAll('.shadow').find(el => el.text().includes('LLM Models'))
      const saveBtn = llmSection!.findAll('button').find(b => b.text() === 'Save')
      await saveBtn!.trigger('click')
      await flushPromises()

      expect(saveTranscriptionModel).toHaveBeenCalledWith('whisper-1')
    })

    it('sends null when empty option is selected for transcription model', async () => {
      fetchMock = mockSettingsAndSkills({ transcription_model: 'whisper-1' })
      vi.stubGlobal('fetch', fetchMock)
      vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
      await transcriptionSelect.setValue('')

      const llmSection = wrapper.findAll('.shadow').find(el => el.text().includes('LLM Models'))
      const saveBtn = llmSection!.findAll('button').find(b => b.text() === 'Save')
      await saveBtn!.trigger('click')
      await flushPromises()

      expect(saveTranscriptionModel).toHaveBeenCalledWith(null)
    })

    it('disables transcription dropdown when no models available', async () => {
      vi.mocked(fetchTranscriptionModels).mockResolvedValue([])

      const { wrapper } = await mountSettings('/settings/tasks')

      const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
      expect((transcriptionSelect.element as HTMLSelectElement).disabled).toBe(true)
      expect(transcriptionSelect.text()).toContain('No transcription models available')
    })

    it('disables transcription dropdown on endpoint failure', async () => {
      vi.mocked(fetchTranscriptionModels).mockRejectedValue(new Error('Failed'))

      const { wrapper } = await mountSettings('/settings/tasks')

      expect(wrapper.text()).toContain('Failed to load transcription models')
      const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
      expect((transcriptionSelect.element as HTMLSelectElement).disabled).toBe(true)
    })

    // --- LLM Timeout ---

    it('renders LLM Timeout input with default value of 30', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      const timeoutInput = wrapper.find('[data-testid="llm-timeout-input"]')
      expect(timeoutInput.exists()).toBe(true)
      expect((timeoutInput.element as HTMLInputElement).value).toBe('30')
    })

    it('loads LLM timeout from settings', async () => {
      fetchMock = mockSettingsAndSkills({ llm_timeout: 60 })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/tasks')

      const timeoutInput = wrapper.find('[data-testid="llm-timeout-input"]')
      expect((timeoutInput.element as HTMLInputElement).value).toBe('60')
    })

    it('saves LLM timeout on Save click', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      const timeoutInput = wrapper.find('[data-testid="llm-timeout-input"]')
      await timeoutInput.setValue(120)

      const llmSection = wrapper.findAll('.shadow').find(el => el.text().includes('LLM Models'))
      const saveBtn = llmSection!.findAll('button').find(b => b.text() === 'Save')
      await saveBtn!.trigger('click')
      await flushPromises()

      expect(saveLlmTimeout).toHaveBeenCalledWith(120)
    })

    it('shows unsaved changes when timeout is modified', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      const llmSection = wrapper.findAll('.shadow').find(el => el.text().includes('LLM Models'))
      expect(llmSection!.text()).not.toContain('Unsaved changes')

      const timeoutInput = wrapper.find('[data-testid="llm-timeout-input"]')
      await timeoutInput.setValue(60)

      expect(llmSection!.text()).toContain('Unsaved changes')
    })

    // --- Task Management Card ---

    it('displays Task Management card with timezone, archive, and log level', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      expect(wrapper.text()).toContain('Timezone')
      expect(wrapper.text()).toContain('Archive after (days)')
      expect(wrapper.text()).toContain('Task Runner Log Level')
    })

    it('renders Task Runner log level dropdown with default INFO', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      const logLevelSelect = wrapper.find('[data-testid="task-runner-log-level-select"]')
      expect(logLevelSelect.exists()).toBe(true)
      expect((logLevelSelect.element as HTMLSelectElement).value).toBe('INFO')

      const options = logLevelSelect.findAll('option')
      const optionValues = options.map(o => o.text())
      expect(optionValues).toEqual(['INFO', 'DEBUG', 'WARNING', 'ERROR'])
    })

    it('loads task runner log level from settings', async () => {
      fetchMock = mockSettingsAndSkills({ task_runner_log_level: 'DEBUG' })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/tasks')

      const logLevelSelect = wrapper.find('[data-testid="task-runner-log-level-select"]')
      expect((logLevelSelect.element as HTMLSelectElement).value).toBe('DEBUG')
    })

    it('saves task management settings (timezone, archive days, log level) on Save click', async () => {
      fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      })
      vi.stubGlobal('fetch', fetchMock)

      const { wrapper } = await mountSettings('/settings/tasks')

      const logLevelSelect = wrapper.find('[data-testid="task-runner-log-level-select"]')
      await logLevelSelect.setValue('ERROR')

      const taskMgmtSection = wrapper.findAll('.shadow').find(el => el.text().includes('Task Management') && el.text().includes('Archive'))
      const saveBtn = taskMgmtSection!.findAll('button').find(b => b.text() === 'Save')
      await saveBtn!.trigger('click')
      await flushPromises()

      const putCall = fetchMock.mock.calls.find(
        (call: any[]) => call[1]?.method === 'PUT' && call[1]?.body?.includes('task_runner_log_level')
      )
      expect(putCall).toBeTruthy()
      const body = JSON.parse(putCall![1].body as string)
      expect(body.task_runner_log_level).toBe('ERROR')
      expect(body.timezone).toBeTruthy()
      expect(body.archive_after_days).toBeTruthy()
      expect(toastMock.success).toHaveBeenCalledWith('Task management settings saved.')
    })

    it('timezone defaults to UTC when no setting exists', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      // Timezone is the 4th select (after title gen, task processing, transcription)
      const tzSelect = selects[3]
      expect((tzSelect.element as HTMLSelectElement).value).toBe('UTC')
    })

    // --- Unsaved changes ---

    it('shows unsaved changes indicator on LLM model modification', async () => {
      vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

      const { wrapper } = await mountSettings('/settings/tasks')

      const selects = wrapper.findAll('select')
      await selects[0].setValue('gpt-4o')
      await nextTick()

      const llmSection = wrapper.findAll('.shadow').find(el => el.text().includes('LLM Models'))
      expect(llmSection!.text()).toContain('Unsaved changes')
    })
  })

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

      expect(wrapper.text()).toContain('System Prompt')
      expect(wrapper.text()).toContain('Skills')
      expect(wrapper.text()).toContain('Skills Repository')
      expect(wrapper.text()).toContain('MCP Server Configuration')
    })

    it('Task Management renders correct components', async () => {
      const { wrapper } = await mountSettings('/settings/tasks')

      expect(wrapper.text()).toContain('LLM Models')
      expect(wrapper.text()).toContain('Task Management')
    })

    it('Security renders correct components', async () => {
      const { wrapper } = await mountSettings('/settings/security')

      expect(wrapper.text()).toContain('Git SSH Key')
      expect(wrapper.text()).toContain('MCP API Key')
    })

    it('Integrations renders correct components', async () => {
      const { wrapper } = await mountSettings('/settings/integrations')

      expect(wrapper.text()).toContain('Platform')
    })
  })
})
