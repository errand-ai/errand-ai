import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LitellmMcpSettings from '../settings/LitellmMcpSettings.vue'

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockFetchLitellmMcpServers = vi.fn()

vi.mock('../../composables/useApi', () => ({
  fetchLitellmMcpServers: (...args: unknown[]) => mockFetchLitellmMcpServers(...args),
}))

const availableResponse = {
  available: true,
  servers: {
    argocd: {
      alias: 'argocd',
      description: 'DevOps ArgoCD',
      tools: ['list_applications', 'get_application', 'sync_application'],
    },
    perplexity: {
      alias: 'perplexity',
      description: 'Perplexity Search',
      tools: ['search'],
    },
  },
  enabled: ['argocd'],
}

const unavailableResponse = {
  available: false,
  servers: {},
  enabled: [],
}

function mountComponent(saveSettings = vi.fn().mockResolvedValue(undefined)) {
  return mount(LitellmMcpSettings, {
    props: { saveSettings },
  })
}

describe('LitellmMcpSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows loading state initially', () => {
    mockFetchLitellmMcpServers.mockReturnValue(new Promise(() => {})) // never resolves
    const wrapper = mountComponent()
    expect(wrapper.find('[data-testid="litellm-mcp-loading"]').exists()).toBe(true)
  })

  it('renders when available with servers', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...availableResponse })
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('[data-testid="litellm-mcp-settings"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('MCP Servers (via LiteLLM)')
    expect(wrapper.find('[data-testid="litellm-server-argocd"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="litellm-server-perplexity"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('3 tools')
    expect(wrapper.text()).toContain('1 tools')
  })

  it('is hidden when unavailable', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...unavailableResponse })
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('[data-testid="litellm-mcp-settings"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="litellm-mcp-loading"]').exists()).toBe(false)
  })

  it('is hidden when fetch fails', async () => {
    mockFetchLitellmMcpServers.mockRejectedValue(new Error('Network error'))
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('[data-testid="litellm-mcp-settings"]').exists()).toBe(false)
  })

  it('reflects enabled state from server response', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...availableResponse })
    const wrapper = mountComponent()
    await flushPromises()

    const argocdCheckbox = wrapper.find('[data-testid="litellm-toggle-argocd"]')
    expect((argocdCheckbox.element as HTMLInputElement).checked).toBe(true)

    const perplexityCheckbox = wrapper.find('[data-testid="litellm-toggle-perplexity"]')
    expect((perplexityCheckbox.element as HTMLInputElement).checked).toBe(false)
  })

  it('toggles server enabled state and shows unsaved indicator', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...availableResponse })
    const wrapper = mountComponent()
    await flushPromises()

    // Toggle perplexity on
    await wrapper.find('[data-testid="litellm-toggle-perplexity"]').setValue(true)

    expect(wrapper.text()).toContain('Unsaved changes')
  })

  it('saves enabled servers via saveSettings', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...availableResponse })
    const saveSettings = vi.fn().mockResolvedValue(undefined)
    const wrapper = mountComponent(saveSettings)
    await flushPromises()

    // Toggle perplexity on
    await wrapper.find('[data-testid="litellm-toggle-perplexity"]').setValue(true)

    // Click save
    await wrapper.find('[data-testid="litellm-mcp-save"]').trigger('click')
    await flushPromises()

    expect(saveSettings).toHaveBeenCalledWith({
      litellm_mcp_servers: expect.arrayContaining(['argocd', 'perplexity']),
    })
  })

  it('refresh button re-fetches servers', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...availableResponse })
    const wrapper = mountComponent()
    await flushPromises()

    expect(mockFetchLitellmMcpServers).toHaveBeenCalledTimes(1)

    // Click refresh
    await wrapper.find('[data-testid="litellm-mcp-refresh"]').trigger('click')
    await flushPromises()

    expect(mockFetchLitellmMcpServers).toHaveBeenCalledTimes(2)
  })

  it('expands server to show tool names', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...availableResponse })
    const wrapper = mountComponent()
    await flushPromises()

    // Tools should not be visible initially
    expect(wrapper.find('[data-testid="litellm-tools-argocd"]').exists()).toBe(false)

    // Click to expand argocd
    const argocdRow = wrapper.find('[data-testid="litellm-server-argocd"]')
    await argocdRow.find('button').trigger('click')

    expect(wrapper.find('[data-testid="litellm-tools-argocd"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('list_applications')
    expect(wrapper.text()).toContain('get_application')
    expect(wrapper.text()).toContain('sync_application')
  })

  it('save button is disabled when no changes', async () => {
    mockFetchLitellmMcpServers.mockResolvedValue({ ...availableResponse })
    const wrapper = mountComponent()
    await flushPromises()

    const saveBtn = wrapper.find('[data-testid="litellm-mcp-save"]')
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(true)
  })
})
