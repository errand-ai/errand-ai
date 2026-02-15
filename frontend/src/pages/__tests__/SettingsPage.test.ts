import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../../stores/auth'
import SettingsPage from '../SettingsPage.vue'

// Mock the useApi functions used by SettingsPage
vi.mock('../../composables/useApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../composables/useApi')>()
  return {
    ...actual,
    fetchLlmModels: vi.fn().mockResolvedValue([]),
    saveLlmModel: vi.fn().mockResolvedValue({}),
    saveTaskProcessingModel: vi.fn().mockResolvedValue({}),
    fetchTranscriptionModels: vi.fn().mockResolvedValue([]),
    saveTranscriptionModel: vi.fn().mockResolvedValue({}),
  }
})

import { fetchLlmModels, saveLlmModel, saveTaskProcessingModel, fetchTranscriptionModels, saveTranscriptionModel } from '../../composables/useApi'

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const adminToken = fakeJwt({
  name: 'Admin',
  resource_access: { 'content-manager': { roles: ['admin'] } },
})

// Helper: build a mock fetch that responds to /api/settings and /api/skills
function mockSettingsAndSkills(
  settingsData: Record<string, unknown> = {},
  skillsData: unknown[] = [],
) {
  return vi.fn().mockImplementation((url: string) => {
    if (url === '/api/skills') {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(skillsData) })
    }
    // Default: /api/settings
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(settingsData) })
  })
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
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // --- Page layout / group headers ---

  it('renders three group headers', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.find('[data-testid="group-agent-configuration"]').text()).toBe('Agent Configuration')
    expect(wrapper.find('[data-testid="group-task-management"]').text()).toBe('Task Management')
    expect(wrapper.find('[data-testid="group-integrations-security"]').text()).toContain('Integrations')
  })

  it('renders both sections after loading', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('System Prompt')
    expect(wrapper.text()).toContain('MCP Server Configuration')
  })

  it('loads existing system prompt into textarea', async () => {
    fetchMock = mockSettingsAndSkills({ system_prompt: 'Hello world' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('Hello world')
  })

  it('saves system prompt on button click', async () => {
    // First call is settings load, second is skills load, third is the PUT
    let callCount = 0
    fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
      callCount++
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      if (_opts?.method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ system_prompt: 'new prompt' }) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    await wrapper.find('textarea').setValue('new prompt')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    const putCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'PUT'
    )
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall![1].body)).toEqual({ system_prompt: 'new prompt' })
    expect(wrapper.text()).toContain('Settings saved.')
  })

  it('shows access denied on 403', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ detail: 'Admin role required' }) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Access denied')
  })

  it('shows error on network failure', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      return Promise.reject(new Error('Network error'))
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load settings')
  })

  // --- MCP Server Configuration ---

  it('MCP section is collapsed by default', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Only the system prompt textarea should be visible (MCP collapsed)
    const textareas = wrapper.findAll('textarea')
    expect(textareas.length).toBe(1)
    expect(wrapper.text()).toContain('MCP Server Configuration')
  })

  it('MCP section expands on click', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

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

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    await mcpButton!.trigger('click')

    const textareas = wrapper.findAll('textarea')
    const mcpTextarea = textareas[textareas.length - 1]
    expect((mcpTextarea.element as HTMLTextAreaElement).value).toContain('test-server')
  })

  it('shows JSON validation error for invalid JSON', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

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

    const wrapper = mount(SettingsPage)
    await flushPromises()

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
    expect(wrapper.text()).toContain('MCP configuration saved.')
  })

  // --- LLM Model Dropdown ---

  it('renders LLM Models section with both dropdowns', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('LLM Models')
    expect(wrapper.text()).toContain('Title Generation Model')
    expect(wrapper.text()).toContain('Task Processing Model')
  })

  it('loads models from fetchLlmModels and populates dropdown', async () => {
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const options = wrapper.findAll('select option')
    const modelOptions = options.map((o) => o.text())
    expect(modelOptions).toContain('claude-haiku-4-5-20251001')
    expect(modelOptions).toContain('gpt-4o')
  })

  it('pre-selects current title generation model from settings', async () => {
    fetchMock = mockSettingsAndSkills({ llm_model: 'gpt-4o' })
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[0].element as HTMLSelectElement).value).toBe('gpt-4o')
  })

  it('saves title generation model on selection change via saveLlmModel', async () => {
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    await selects[0].setValue('gpt-4o')
    await flushPromises()

    expect(saveLlmModel).toHaveBeenCalledWith('gpt-4o')
  })

  it('shows error when model list fails to load', async () => {
    vi.mocked(fetchLlmModels).mockRejectedValue(new Error('Failed'))

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load available models')
  })

  it('defaults to claude-haiku when no llm_model in settings', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[0].element as HTMLSelectElement).value).toBe('claude-haiku-4-5-20251001')
  })

  // --- Task Processing Model Dropdown ---

  it('loads task processing model from settings', async () => {
    fetchMock = mockSettingsAndSkills({ task_processing_model: 'gpt-4o' })
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-sonnet-4-5-20250929', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[1].element as HTMLSelectElement).value).toBe('gpt-4o')
  })

  it('defaults task processing model to claude-sonnet when not in settings', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[1].element as HTMLSelectElement).value).toBe('claude-sonnet-4-5-20250929')
  })

  it('saves task processing model on selection change via saveTaskProcessingModel', async () => {
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-sonnet-4-5-20250929', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    await selects[1].setValue('gpt-4o')
    await flushPromises()

    expect(saveTaskProcessingModel).toHaveBeenCalledWith('gpt-4o')
  })

  it('disables both dropdowns when models endpoint fails', async () => {
    vi.mocked(fetchLlmModels).mockRejectedValue(new Error('Failed'))

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[0].element as HTMLSelectElement).disabled).toBe(true)
    expect((selects[1].element as HTMLSelectElement).disabled).toBe(true)
  })

  // --- MCP Configuration Validation ---

  it('rejects STDIO MCP server configuration', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

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
    const wrapper = mount(SettingsPage)
    await flushPromises()

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

  it('rejects mixed valid and STDIO servers', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    await mcpButton!.trigger('click')

    const textareas = wrapper.findAll('textarea')
    const mcpTextarea = textareas[textareas.length - 1]
    await mcpTextarea.setValue(JSON.stringify({
      mcpServers: {
        argocd: { url: 'http://localhost:4000/argocd/mcp' },
        local: { command: 'npx', args: ['-y', 'some-server'] },
      },
    }))

    const saveButtons = wrapper.findAll('button')
    const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
    await saveMcpButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('STDIO transport')
    expect(wrapper.text()).toContain("Server 'local'")
  })

  it('accepts valid HTTP Streaming MCP configuration', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

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

    expect(wrapper.text()).toContain('MCP configuration saved.')
  })

  it('rejects malformed JSON in MCP config', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    await mcpButton!.trigger('click')

    const textareas = wrapper.findAll('textarea')
    const mcpTextarea = textareas[textareas.length - 1]
    await mcpTextarea.setValue('{invalid json}}}')

    const saveButtons = wrapper.findAll('button')
    const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
    await saveMcpButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Invalid JSON')
  })

  // --- Timezone Selector ---

  it('displays timezone selector on settings page', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Timezone')
    const selects = wrapper.findAll('select')
    expect(selects.length).toBeGreaterThanOrEqual(5)
  })

  it('timezone populated from settings', async () => {
    fetchMock = mockSettingsAndSkills({ timezone: 'Europe/London' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    const tzSelect = selects[4]
    expect((tzSelect.element as HTMLSelectElement).value).toBe('Europe/London')
  })

  it('timezone defaults to UTC when no setting exists', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    const tzSelect = selects[4]
    expect((tzSelect.element as HTMLSelectElement).value).toBe('UTC')
  })

  it('selecting a timezone triggers save to API', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    const tzSelect = selects[4]
    await tzSelect.setValue('Europe/London')
    await flushPromises()

    const putCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'PUT' && call[1]?.body?.includes('timezone')
    )
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall![1].body as string)).toEqual({ timezone: 'Europe/London' })
    expect(wrapper.text()).toContain('Timezone saved.')
  })

  // --- Task Runner Log Level Dropdown ---

  it('renders Task Runner log level dropdown with default INFO', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Task Runner')
    expect(wrapper.text()).toContain('Log Level')
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

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const logLevelSelect = wrapper.find('[data-testid="task-runner-log-level-select"]')
    expect((logLevelSelect.element as HTMLSelectElement).value).toBe('DEBUG')
  })

  it('saves task runner log level on selection change', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const logLevelSelect = wrapper.find('[data-testid="task-runner-log-level-select"]')
    await logLevelSelect.setValue('ERROR')
    await flushPromises()

    const putCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'PUT' && call[1]?.body?.includes('task_runner_log_level')
    )
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall![1].body as string)).toEqual({ task_runner_log_level: 'ERROR' })
    expect(wrapper.text()).toContain('Log level saved.')
  })

  // --- Transcription Model Dropdown ---

  it('renders Transcription Model dropdown with filtered models', async () => {
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

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

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).value).toBe('')
    expect(transcriptionSelect.text()).toContain('Select a model to enable voice input')
  })

  it('loads current transcription model from settings', async () => {
    fetchMock = mockSettingsAndSkills({ transcription_model: 'whisper-large-v3' })
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).value).toBe('whisper-large-v3')
  })

  it('saves transcription model on selection change', async () => {
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    await transcriptionSelect.setValue('whisper-1')
    await flushPromises()

    expect(saveTranscriptionModel).toHaveBeenCalledWith('whisper-1')
  })

  it('sends null when Disabled option is selected for transcription model', async () => {
    fetchMock = mockSettingsAndSkills({ transcription_model: 'whisper-1' })
    vi.stubGlobal('fetch', fetchMock)
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    await transcriptionSelect.setValue('')
    await flushPromises()

    expect(saveTranscriptionModel).toHaveBeenCalledWith(null)
  })

  it('disables transcription dropdown when no models available', async () => {
    vi.mocked(fetchTranscriptionModels).mockResolvedValue([])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).disabled).toBe(true)
    expect(transcriptionSelect.text()).toContain('No transcription models available')
  })

  it('disables transcription dropdown on endpoint failure', async () => {
    vi.mocked(fetchTranscriptionModels).mockRejectedValue(new Error('Failed'))

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load transcription models')
    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).disabled).toBe(true)
  })

  // --- MCP API Key Section ---

  it('shows MCP API Key section with masked key when key exists', async () => {
    fetchMock = mockSettingsAndSkills({ mcp_api_key: 'abc123def456' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('MCP API Key')
    expect(wrapper.text()).toContain('API Key')
    const codeEl = wrapper.find('code')
    expect(codeEl.text()).toBe('\u2022'.repeat(32))
  })

  it('shows placeholder message when no API key exists', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('No API key generated')
  })

  it('reveals and hides API key on toggle', async () => {
    fetchMock = mockSettingsAndSkills({ mcp_api_key: 'secret-key-value' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

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

    const wrapper = mount(SettingsPage)
    await flushPromises()

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

    const wrapper = mount(SettingsPage, { attachTo: document.body })
    await flushPromises()

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
    expect(wrapper.text()).toContain('API key regenerated.')

    wrapper.unmount()
  })

  it('does not regenerate when dialog is cancelled', async () => {
    fetchMock = mockSettingsAndSkills({ mcp_api_key: 'old-key-123' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage, { attachTo: document.body })
    await flushPromises()

    const regenBtn = wrapper.find('[data-testid="mcp-key-regenerate"]')
    await regenBtn.trigger('click')
    await flushPromises()

    const cancelBtn = wrapper.find('[data-testid="mcp-regenerate-cancel"]')
    expect(cancelBtn.exists()).toBe(true)
    await cancelBtn.trigger('click')
    await flushPromises()

    // Only the initial GET calls (settings + skills)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })

  it('renders example MCP configuration with masked key', async () => {
    fetchMock = mockSettingsAndSkills({ mcp_api_key: 'test-api-key' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Example MCP Configuration')
    expect(wrapper.text()).toContain('content-manager')
    expect(wrapper.text()).toContain('/mcp')
    expect(wrapper.text()).toContain('Bearer ' + '*'.repeat(32))
    expect(wrapper.text()).not.toContain('Bearer test-api-key')
  })

  it('copies example config to clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText: writeTextMock } })

    fetchMock = mockSettingsAndSkills({ mcp_api_key: 'cfg-key' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const copyConfigBtn = wrapper.find('[data-testid="mcp-config-copy"]')
    expect(copyConfigBtn.text()).toBe('Copy Configuration')

    await copyConfigBtn.trigger('click')
    await flushPromises()

    expect(writeTextMock).toHaveBeenCalled()
    const copiedText = writeTextMock.mock.calls[0][0]
    const parsed = JSON.parse(copiedText)
    expect(parsed.mcpServers['content-manager'].url).toContain('/mcp')
    expect(parsed.mcpServers['content-manager'].headers.Authorization).toBe('Bearer cfg-key')
    expect(copyConfigBtn.text()).toBe('Copied!')
  })

  // --- Skills Section (new API-based) ---

  it('shows Skills section always visible with skill list', async () => {
    fetchMock = mockSettingsAndSkills({}, [
      { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [], created_at: '', updated_at: '' },
      { id: '2', name: 'coder', description: 'Code generation', instructions: 'Code text', files: [], created_at: '', updated_at: '' },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Skills section is always visible (no need to expand)
    expect(wrapper.text()).toContain('Skills')
    expect(wrapper.text()).toContain('(2)')
    expect(wrapper.text()).toContain('researcher')
    expect(wrapper.text()).toContain('Web research')
    expect(wrapper.text()).toContain('coder')
    expect(wrapper.text()).toContain('Code generation')
  })

  it('shows Agent Skills standard description text', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Agent Skills standard')
    expect(wrapper.text()).toContain('SKILL.md')
  })

  it('shows empty state when no skills defined', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

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

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Click Add Skill
    const addBtn = wrapper.find('[data-testid="skill-add"]')
    await addBtn.trigger('click')

    // Fill in the form
    await wrapper.find('[data-testid="skill-name-input"]').setValue('researcher')
    await wrapper.find('[data-testid="skill-description-input"]').setValue('Web research')
    await wrapper.find('[data-testid="skill-instructions-input"]').setValue('You are a researcher.')

    // Click save
    await wrapper.find('[data-testid="skill-save"]').trigger('click')
    await flushPromises()

    // Verify POST was called
    const postCall = fetchMock.mock.calls.find(
      (call: any[]) => call[0] === '/api/skills' && call[1]?.method === 'POST'
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall![1].body as string)
    expect(body.name).toBe('researcher')
    expect(body.description).toBe('Web research')
    expect(body.instructions).toBe('You are a researcher.')
  })

  it('deletes a skill via DELETE /api/skills/{id}', async () => {
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

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Click delete
    const deleteBtn = wrapper.find('[data-testid="skill-delete"]')
    await deleteBtn.trigger('click')
    await flushPromises()

    // Verify DELETE was called
    const deleteCall = fetchMock.mock.calls.find(
      (call: any[]) => call[0] === '/api/skills/1' && call[1]?.method === 'DELETE'
    )
    expect(deleteCall).toBeTruthy()
  })

  it('shows name validation error for invalid name in real-time', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const addBtn = wrapper.find('[data-testid="skill-add"]')
    await addBtn.trigger('click')

    const nameInput = wrapper.find('[data-testid="skill-name-input"]')
    await nameInput.setValue('Invalid Name')
    await nameInput.trigger('input')
    await flushPromises()

    expect(wrapper.text()).toContain('Name must be lowercase')
  })

  it('shows name validation error for consecutive hyphens', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const addBtn = wrapper.find('[data-testid="skill-add"]')
    await addBtn.trigger('click')

    const nameInput = wrapper.find('[data-testid="skill-name-input"]')
    await nameInput.setValue('my--skill')
    await nameInput.trigger('input')
    await flushPromises()

    expect(wrapper.text()).toContain('consecutive hyphens')
  })

  it('shows description character counter', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const addBtn = wrapper.find('[data-testid="skill-add"]')
    await addBtn.trigger('click')

    const charCount = wrapper.find('[data-testid="description-char-count"]')
    expect(charCount.text()).toBe('0/1024')

    await wrapper.find('[data-testid="skill-description-input"]').setValue('Hello world')
    await flushPromises()

    expect(charCount.text()).toBe('11/1024')
  })

  it('shows name validation hint text', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const addBtn = wrapper.find('[data-testid="skill-add"]')
    await addBtn.trigger('click')

    expect(wrapper.text()).toContain('Lowercase letters, digits, and hyphens only')
    expect(wrapper.text()).toContain('Max 64 characters')
  })

  // --- Git SSH Key Section ---

  it('shows SSH public key when key exists', async () => {
    fetchMock = mockSettingsAndSkills({ ssh_public_key: 'ssh-ed25519 AAAA content-manager' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Git SSH Key')
    const keyEl = wrapper.find('[data-testid="ssh-public-key"]')
    expect(keyEl.exists()).toBe(true)
    expect(keyEl.text()).toBe('ssh-ed25519 AAAA content-manager')
  })

  it('shows no-key message when SSH key is absent', async () => {
    const wrapper = mount(SettingsPage)
    await flushPromises()

    const noKey = wrapper.find('[data-testid="ssh-no-key"]')
    expect(noKey.exists()).toBe(true)
    expect(noKey.text()).toContain('No SSH key generated')
  })

  it('copies SSH public key to clipboard', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText: writeTextMock } })

    fetchMock = mockSettingsAndSkills({ ssh_public_key: 'ssh-ed25519 COPY content-manager' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const copyBtn = wrapper.find('[data-testid="ssh-key-copy"]')
    expect(copyBtn.text()).toBe('Copy')

    await copyBtn.trigger('click')
    await flushPromises()

    expect(writeTextMock).toHaveBeenCalledWith('ssh-ed25519 COPY content-manager')
    expect(copyBtn.text()).toBe('Copied!')
  })

  it('regenerates SSH key on confirm via dialog', async () => {
    fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      if (url === '/api/settings/regenerate-ssh-key') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ssh_public_key: 'ssh-ed25519 NEW content-manager' }) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ssh_public_key: 'ssh-ed25519 OLD content-manager' }) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage, { attachTo: document.body })
    await flushPromises()

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
    expect(postCall![1].method).toBe('POST')

    const keyEl = wrapper.find('[data-testid="ssh-public-key"]')
    expect(keyEl.text()).toBe('ssh-ed25519 NEW content-manager')
    expect(wrapper.text()).toContain('SSH key regenerated.')

    wrapper.unmount()
  })

  it('does not regenerate SSH key when dialog is cancelled', async () => {
    fetchMock = mockSettingsAndSkills({ ssh_public_key: 'ssh-ed25519 KEEP content-manager' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage, { attachTo: document.body })
    await flushPromises()

    const regenBtn = wrapper.find('[data-testid="ssh-key-regenerate"]')
    await regenBtn.trigger('click')
    await flushPromises()

    const cancelBtn = wrapper.find('[data-testid="ssh-regenerate-cancel"]')
    expect(cancelBtn.exists()).toBe(true)
    await cancelBtn.trigger('click')
    await flushPromises()

    // Only the initial GET calls (settings + skills)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })

  it('displays default SSH hosts from settings', async () => {
    fetchMock = mockSettingsAndSkills({
      ssh_public_key: 'ssh-ed25519 AAAA content-manager',
      git_ssh_hosts: ['github.com', 'bitbucket.org'],
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('github.com')
    expect(wrapper.text()).toContain('bitbucket.org')
  })

  it('adds a new SSH host', async () => {
    fetchMock = mockSettingsAndSkills({
      ssh_public_key: 'ssh-ed25519 AAAA content-manager',
      git_ssh_hosts: ['github.com'],
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const input = wrapper.find('[data-testid="ssh-host-input"]')
    await input.setValue('gitlab.com')
    const addBtn = wrapper.find('[data-testid="ssh-host-add"]')
    await addBtn.trigger('click')

    expect(wrapper.text()).toContain('gitlab.com')
    expect(wrapper.text()).toContain('github.com')
  })

  it('removes an SSH host', async () => {
    fetchMock = mockSettingsAndSkills({
      ssh_public_key: 'ssh-ed25519 AAAA content-manager',
      git_ssh_hosts: ['github.com', 'bitbucket.org'],
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const removeBtns = wrapper.findAll('[data-testid="ssh-host-remove"]')
    expect(removeBtns).toHaveLength(2)
    await removeBtns[0].trigger('click')

    expect(wrapper.text()).not.toContain('github.com')
    expect(wrapper.text()).toContain('bitbucket.org')
  })

  it('prevents adding a duplicate SSH host', async () => {
    fetchMock = mockSettingsAndSkills({
      ssh_public_key: 'ssh-ed25519 AAAA content-manager',
      git_ssh_hosts: ['github.com'],
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const input = wrapper.find('[data-testid="ssh-host-input"]')
    await input.setValue('github.com')
    const addBtn = wrapper.find('[data-testid="ssh-host-add"]')
    await addBtn.trigger('click')

    expect(wrapper.text()).toContain('already in the list')
  })

  it('prevents adding an empty SSH host', async () => {
    fetchMock = mockSettingsAndSkills({
      ssh_public_key: 'ssh-ed25519 AAAA content-manager',
      git_ssh_hosts: ['github.com'],
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const input = wrapper.find('[data-testid="ssh-host-input"]')
    await input.setValue('   ')
    const addBtn = wrapper.find('[data-testid="ssh-host-add"]')
    await addBtn.trigger('click')

    const removeBtns = wrapper.findAll('[data-testid="ssh-host-remove"]')
    expect(removeBtns).toHaveLength(1)
  })

  it('saves SSH hosts via PUT', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
        ssh_public_key: 'ssh-ed25519 AAAA content-manager',
        git_ssh_hosts: ['github.com', 'bitbucket.org'],
      }) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const saveBtn = wrapper.find('[data-testid="ssh-hosts-save"]')
    await saveBtn.trigger('click')
    await flushPromises()

    const putCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'PUT' && call[1]?.body?.includes('git_ssh_hosts')
    )
    expect(putCall).toBeTruthy()
    const body = JSON.parse(putCall![1].body as string)
    expect(body.git_ssh_hosts).toEqual(['github.com', 'bitbucket.org'])
    expect(wrapper.text()).toContain('SSH hosts saved.')
  })

  it('shows deploy key help text', async () => {
    fetchMock = mockSettingsAndSkills({ ssh_public_key: 'ssh-ed25519 AAAA content-manager' })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('deploy key')
    expect(wrapper.text()).toContain('write access')
  })

  // --- File management ---

  it('shows file count per skill', async () => {
    fetchMock = mockSettingsAndSkills({}, [
      { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [
        { id: 'f1', path: 'scripts/extract.py', created_at: '' },
        { id: 'f2', path: 'references/guide.md', created_at: '' },
      ], created_at: '', updated_at: '' },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('2 file(s)')
  })

  it('toggles file panel on Files button click', async () => {
    fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === '/api/skills/1') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [{ id: 'f1', path: 'scripts/extract.py', content: '#!/bin/bash', created_at: '' }] }) })
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [{ id: 'f1', path: 'scripts/extract.py', created_at: '' }], created_at: '', updated_at: '' }]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Files panel should not be visible initially
    expect(wrapper.find('[data-testid="skill-files-panel"]').exists()).toBe(false)

    // Click Files toggle
    const filesToggle = wrapper.find('[data-testid="skill-files-toggle"]')
    await filesToggle.trigger('click')
    await flushPromises()

    // Panel should be visible with grouped files
    expect(wrapper.find('[data-testid="skill-files-panel"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('scripts/')
    expect(wrapper.text()).toContain('extract.py')
  })

  it('submits file add form via POST', async () => {
    const skillDetail = { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [{ id: 'f1', path: 'scripts/extract.py', content: '#!/bin/bash', created_at: '' }] }
    fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
      if (url === '/api/skills/1/files' && _opts?.method === 'POST') return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: 'f2', path: 'references/guide.md', content: '# Guide', created_at: '' }) })
      if (url === '/api/skills/1') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(skillDetail) })
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ ...skillDetail, files: [{ id: 'f1', path: 'scripts/extract.py', created_at: '' }], created_at: '', updated_at: '' }]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Open files panel
    await wrapper.find('[data-testid="skill-files-toggle"]').trigger('click')
    await flushPromises()

    // Click Add File button
    await wrapper.find('[data-testid="file-add"]').trigger('click')
    await flushPromises()

    // Fill form
    await wrapper.find('[data-testid="file-filename-input"]').setValue('guide.md')
    await wrapper.find('[data-testid="file-content-input"]').setValue('# Guide')

    // Submit
    await wrapper.find('[data-testid="file-save"]').trigger('click')
    await flushPromises()

    // Verify POST was called with correct path
    const postCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'POST' && call[0]?.includes('/files')
    )
    expect(postCall).toBeTruthy()
    const body = JSON.parse(postCall![1].body as string)
    expect(body.path).toBe('scripts/guide.md')
    expect(body.content).toBe('# Guide')
  })

  it('deletes a file via DELETE', async () => {
    const skillDetail = { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [{ id: 'f1', path: 'scripts/extract.py', content: '#!/bin/bash', created_at: '' }] }
    fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
      if (url === '/api/skills/1/files/f1' && _opts?.method === 'DELETE') return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) })
      if (url === '/api/skills/1') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(skillDetail) })
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ ...skillDetail, files: [{ id: 'f1', path: 'scripts/extract.py', created_at: '' }], created_at: '', updated_at: '' }]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Open files panel
    await wrapper.find('[data-testid="skill-files-toggle"]').trigger('click')
    await flushPromises()

    // Click delete on the file
    await wrapper.find('[data-testid="file-delete"]').trigger('click')
    await flushPromises()

    // Verify DELETE was called
    const deleteCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'DELETE' && call[0]?.includes('/files/')
    )
    expect(deleteCall).toBeTruthy()
    expect(deleteCall![0]).toContain('/api/skills/1/files/f1')
  })

  // --- Skill edit ---

  it('opens edit form and submits PUT for existing skill', async () => {
    fetchMock = mockSettingsAndSkills({}, [
      { id: '1', name: 'researcher', description: 'Web research', instructions: 'Full text', files: [], created_at: '', updated_at: '' },
    ])
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Click Edit button
    await wrapper.find('[data-testid="skill-edit"]').trigger('click')
    await flushPromises()

    // Form should be populated with existing values
    const nameInput = wrapper.find('[data-testid="skill-name-input"]')
    expect((nameInput.element as HTMLInputElement).value).toBe('researcher')

    // Update fetch to handle PUT
    fetchMock = vi.fn().mockImplementation((url: string, _opts?: RequestInit) => {
      if (url === '/api/skills/1' && _opts?.method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ id: '1', name: 'researcher-v2', description: 'Updated', instructions: 'New text' }) })
      if (url === '/api/skills') return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([{ id: '1', name: 'researcher-v2', description: 'Updated', instructions: 'New text', files: [], created_at: '', updated_at: '' }]) })
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    // Modify and submit
    await nameInput.setValue('researcher-v2')
    await wrapper.find('[data-testid="skill-description-input"]').setValue('Updated')
    await wrapper.find('[data-testid="skill-instructions-input"]').setValue('New text')
    await wrapper.find('[data-testid="skill-save"]').trigger('click')
    await flushPromises()

    // Verify PUT was called
    const putCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'PUT' && call[0]?.includes('/api/skills/1')
    )
    expect(putCall).toBeTruthy()
    const body = JSON.parse(putCall![1].body as string)
    expect(body.name).toBe('researcher-v2')
    expect(body.description).toBe('Updated')
    expect(body.instructions).toBe('New text')
  })
})
