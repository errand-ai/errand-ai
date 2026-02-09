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
  }
})

import { fetchLlmModels, saveLlmModel } from '../../composables/useApi'

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

  it('displays MCP servers as formatted JSON when present', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ mcp_servers: [{ name: 'test-server' }] }),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('test-server')
    expect(wrapper.find('pre').exists()).toBe(true)
  })

  // --- LLM Model Dropdown ---

  it('renders LLM Model section', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })

    const wrapper = mount(SettingsPage)
    await flushPromises()

    expect(wrapper.text()).toContain('LLM Model')
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

  it('pre-selects current model from settings', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ llm_model: 'gpt-4o' }),
    })
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    // Find the LLM model select (second select on the page, after status selects)
    const selects = wrapper.findAll('select')
    const llmSelect = selects[selects.length - 1]
    expect((llmSelect.element as HTMLSelectElement).value).toBe('gpt-4o')
  })

  it('saves model on selection change via saveLlmModel', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({}),
    })
    vi.mocked(fetchLlmModels).mockResolvedValue(['claude-haiku-4-5-20251001', 'gpt-4o'])

    const wrapper = mount(SettingsPage)
    await flushPromises()

    const selects = wrapper.findAll('select')
    const llmSelect = selects[selects.length - 1]
    await llmSelect.setValue('gpt-4o')
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

    // With no models loaded, the dropdown shows the default
    const selects = wrapper.findAll('select')
    const llmSelect = selects[selects.length - 1]
    expect((llmSelect.element as HTMLSelectElement).value).toBe('claude-haiku-4-5-20251001')
  })
})
