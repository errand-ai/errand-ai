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

describe('SettingsPage', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.setToken(adminToken)
    fetchMock = vi.fn()
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

  it('renders both sections after loading', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('System Prompt')
    expect(wrapper.text()).toContain('MCP Server Configuration')
  })

  it('loads existing system prompt into textarea', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ system_prompt: 'Hello world' }),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('Hello world')
  })

  it('saves system prompt on button click', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ system_prompt: 'new prompt' }),
      })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    await wrapper.find('textarea').setValue('new prompt')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [url, opts] = fetchMock.mock.calls[1]
    expect(url).toBe('/api/settings')
    expect(opts.method).toBe('PUT')
    expect(JSON.parse(opts.body)).toEqual({ system_prompt: 'new prompt' })
    expect(wrapper.text()).toContain('Settings saved.')
  })

  it('shows access denied on 403', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'Admin role required' }),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Access denied')
  })

  it('shows error on network failure', async () => {
    fetchMock.mockRejectedValueOnce(new Error('Network error'))

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load settings')
  })

  // --- MCP Server Configuration ---

  it('MCP section is collapsed by default', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ mcp_servers: { servers: [] } }),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // The MCP textarea should not be visible when collapsed
    const textareas = wrapper.findAll('textarea')
    // Only the system prompt textarea should be visible
    expect(textareas.length).toBe(1)
    expect(wrapper.text()).toContain('MCP Server Configuration')
  })

  it('MCP section expands on click', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ mcp_servers: { servers: [] } }),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Click the MCP header button to expand
    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    expect(mcpButton).toBeTruthy()
    await mcpButton!.trigger('click')

    // Now the MCP textarea should be visible (2 textareas total)
    const textareas = wrapper.findAll('textarea')
    expect(textareas.length).toBe(2)
  })

  it('loads MCP servers into text box when expanded', async () => {
    const mcpConfig = { servers: [{ name: 'test-server' }] }
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ mcp_servers: mcpConfig }),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Expand MCP section
    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    await mcpButton!.trigger('click')

    const textareas = wrapper.findAll('textarea')
    const mcpTextarea = textareas[textareas.length - 1]
    expect((mcpTextarea.element as HTMLTextAreaElement).value).toContain('test-server')
  })

  it('shows JSON validation error for invalid JSON', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Expand MCP section
    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    await mcpButton!.trigger('click')

    // Enter invalid JSON
    const textareas = wrapper.findAll('textarea')
    const mcpTextarea = textareas[textareas.length - 1]
    await mcpTextarea.setValue('not valid json {{{')

    // Click save
    const saveButtons = wrapper.findAll('button')
    const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
    await saveMcpButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Invalid JSON')
  })

  it('saves valid MCP JSON configuration', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Expand MCP section
    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    await mcpButton!.trigger('click')

    // Enter valid JSON
    const textareas = wrapper.findAll('textarea')
    const mcpTextarea = textareas[textareas.length - 1]
    await mcpTextarea.setValue('{"mcpServers": {"test": {"url": "http://localhost:4000/mcp"}}}')

    // Click save
    const saveButtons = wrapper.findAll('button')
    const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
    await saveMcpButton!.trigger('click')
    await flushPromises()

    // Verify the PUT was called with parsed JSON
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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('LLM Models')
    expect(wrapper.text()).toContain('Title Generation Model')
    expect(wrapper.text()).toContain('Task Processing Model')
  })

  it('loads models from fetchLlmModels and populates dropdown', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const options = wrapper.findAll('select option')
    const modelOptions = options.map((o) => o.text())
    expect(modelOptions).toContain('claude-haiku-4-5-20251001')
    expect(modelOptions).toContain('gpt-4o')
  })

  it('pre-selects current title generation model from settings', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ llm_model: 'gpt-4o' }),
    })
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    // First select is title generation model
    expect((selects[0].element as HTMLSelectElement).value).toBe('gpt-4o')
  })

  it('saves title generation model on selection change via saveLlmModel', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    await selects[0].setValue('gpt-4o')
    await flushPromises()

    expect(saveLlmModel).toHaveBeenCalledWith('gpt-4o')
  })

  it('shows error when model list fails to load', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchLlmModels).mockRejectedValue(new Error('Failed'))

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load available models')
  })

  it('defaults to claude-haiku when no llm_model in settings', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[0].element as HTMLSelectElement).value).toBe('claude-haiku-4-5-20251001')
  })

  // --- Task Processing Model Dropdown ---

  it('loads task processing model from settings', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ task_processing_model: 'gpt-4o' }),
    })
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-sonnet-4-5-20250929', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    // Second select is task processing model
    expect((selects[1].element as HTMLSelectElement).value).toBe('gpt-4o')
  })

  it('defaults task processing model to claude-sonnet when not in settings', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[1].element as HTMLSelectElement).value).toBe('claude-sonnet-4-5-20250929')
  })

  it('saves task processing model on selection change via saveTaskProcessingModel', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-sonnet-4-5-20250929', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    await selects[1].setValue('gpt-4o')
    await flushPromises()

    expect(saveTaskProcessingModel).toHaveBeenCalledWith('gpt-4o')
  })

  it('disables both dropdowns when models endpoint fails', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchLlmModels).mockRejectedValue(new Error('Failed'))

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    expect((selects[0].element as HTMLSelectElement).disabled).toBe(true)
    expect((selects[1].element as HTMLSelectElement).disabled).toBe(true)
  })

  // --- MCP Configuration Validation ---

  it('rejects STDIO MCP server configuration', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Expand MCP section
    const buttons = wrapper.findAll('button')
    const mcpButton = buttons.find(b => b.text().includes('MCP Server Configuration'))
    await mcpButton!.trigger('click')

    // Enter STDIO config
    const textareas = wrapper.findAll('textarea')
    const mcpTextarea = textareas[textareas.length - 1]
    await mcpTextarea.setValue(JSON.stringify({
      mcpServers: { local: { command: 'npx', args: ['-y', 'some-mcp-server'] } },
    }))

    // Click save
    const saveButtons = wrapper.findAll('button')
    const saveMcpButton = saveButtons.find(b => b.text().includes('Save MCP Config'))
    await saveMcpButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('STDIO transport')
    expect(wrapper.text()).toContain("Server 'local'")
  })

  it('rejects MCP server entry missing url field', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

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
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })

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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Timezone')
    // Find the timezone select (fourth select after title gen, task processing, and transcription model)
    const selects = wrapper.findAll('select')
    expect(selects.length).toBeGreaterThanOrEqual(4)
  })

  it('timezone populated from settings', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ timezone: 'Europe/London' }),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    const tzSelect = selects[3]
    expect((tzSelect.element as HTMLSelectElement).value).toBe('Europe/London')
  })

  it('timezone defaults to UTC when no setting exists', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    // Fourth select is timezone (after title gen, task processing, transcription)
    const tzSelect = selects[3]
    expect((tzSelect.element as HTMLSelectElement).value).toBe('UTC')
  })

  it('selecting a timezone triggers save to API', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ timezone: 'Europe/London' }),
      })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    const tzSelect = selects[3]
    await tzSelect.setValue('Europe/London')
    await flushPromises()

    // Verify the PUT call
    const putCall = fetchMock.mock.calls.find(
      (call: any[]) => call[1]?.method === 'PUT' && call[1]?.body?.includes('timezone')
    )
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall![1].body as string)).toEqual({ timezone: 'Europe/London' })
    expect(wrapper.text()).toContain('Timezone saved.')
  })

  // --- Transcription Model Dropdown ---

  it('renders Transcription Model dropdown with filtered models', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).value).toBe('')
    expect(transcriptionSelect.text()).toContain('Select a model to enable voice input')
  })

  it('loads current transcription model from settings', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ transcription_model: 'whisper-large-v3' }),
    })
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).value).toBe('whisper-large-v3')
  })

  it('saves transcription model on selection change', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1', 'whisper-large-v3'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    await transcriptionSelect.setValue('whisper-1')
    await flushPromises()

    expect(saveTranscriptionModel).toHaveBeenCalledWith('whisper-1')
  })

  it('sends null when Disabled option is selected for transcription model', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ transcription_model: 'whisper-1' }),
    })
    vi.mocked(fetchTranscriptionModels).mockResolvedValue(['whisper-1'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    await transcriptionSelect.setValue('')
    await flushPromises()

    expect(saveTranscriptionModel).toHaveBeenCalledWith(null)
  })

  it('disables transcription dropdown when no models available', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchTranscriptionModels).mockResolvedValue([])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).disabled).toBe(true)
    expect(transcriptionSelect.text()).toContain('No transcription models available')
  })

  it('disables transcription dropdown on endpoint failure', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchTranscriptionModels).mockRejectedValue(new Error('Failed'))

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load transcription models')
    const transcriptionSelect = wrapper.find('[data-testid="transcription-model-select"]')
    expect((transcriptionSelect.element as HTMLSelectElement).disabled).toBe(true)
  })
})
