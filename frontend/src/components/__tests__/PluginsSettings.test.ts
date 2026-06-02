import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PluginsSettings from '../settings/PluginsSettings.vue'

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const apiMocks = {
  fetchPlugins: vi.fn(),
  patchPlugin: vi.fn(),
  deletePlugin: vi.fn(),
  updatePlugin: vi.fn(),
  installPlugin: vi.fn(),
  fetchMarketplaces: vi.fn(),
  fetchMarketplacePlugins: vi.fn(),
  fetchCredentials: vi.fn(),
}

vi.mock('../../composables/useApi', () => ({
  fetchPlugins: (...args: unknown[]) => apiMocks.fetchPlugins(...args),
  patchPlugin: (...args: unknown[]) => apiMocks.patchPlugin(...args),
  deletePlugin: (...args: unknown[]) => apiMocks.deletePlugin(...args),
  updatePlugin: (...args: unknown[]) => apiMocks.updatePlugin(...args),
  installPlugin: (...args: unknown[]) => apiMocks.installPlugin(...args),
  fetchMarketplaces: (...args: unknown[]) => apiMocks.fetchMarketplaces(...args),
  fetchMarketplacePlugins: (...args: unknown[]) => apiMocks.fetchMarketplacePlugins(...args),
  fetchCredentials: (...args: unknown[]) => apiMocks.fetchCredentials(...args),
}))

const slackPlugin = {
  id: 'pl-1',
  plugin_name: 'slack-toolkit',
  marketplace_id: 'mp-1',
  marketplace_name: 'acme-public',
  installed_version: '1.2.0',
  latest_available_version: '1.3.0',
  enabled: true,
  manifest: null,
  ignored_artifacts: [{ type: 'hooks', count: 2 }, { type: 'commands', count: 1 }],
  skill_conflicts: [{ skill: 'post-message', other: 'team-chat' }],
  update_available: true,
  skills: ['post-message', 'list-channels'],
  mcp_servers: [{ raw: 'slack', namespaced: 'slack-toolkit__slack' }],
  installed_at: '2026-01-01T00:00:00Z',
  last_checked_at: '2026-06-01T00:00:00Z',
}

const noUpdatePlugin = {
  ...slackPlugin,
  id: 'pl-2',
  plugin_name: 'research-pack',
  marketplace_id: null,
  marketplace_name: null,
  installed_version: '0.5.0',
  latest_available_version: '0.5.0',
  enabled: false,
  ignored_artifacts: null,
  skill_conflicts: null,
  update_available: false,
  skills: [],
  mcp_servers: [],
}

async function mountComponent() {
  apiMocks.fetchPlugins.mockResolvedValue([slackPlugin, noUpdatePlugin])
  const wrapper = mount(PluginsSettings)
  await flushPromises()
  return wrapper
}

describe('PluginsSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('lists plugins with update badge and conflict indicator', async () => {
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="plugin-card-pl-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plugin-update-badge-pl-1"]').text()).toContain('1.3.0')
    expect(wrapper.find('[data-testid="plugin-conflict-badge-pl-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plugin-update-badge-pl-2"]').exists()).toBe(false)
  })

  it('expanding a card shows skills, MCP pairs and ignored artifacts', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="plugin-toggle-expand-pl-1"]').trigger('click')
    const details = wrapper.find('[data-testid="plugin-details-pl-1"]')
    expect(details.exists()).toBe(true)
    expect(details.text()).toContain('post-message')
    expect(details.text()).toContain('slack')
    expect(details.text()).toContain('slack-toolkit__slack')
    expect(details.text()).toContain('2 hooks')
    expect(details.text()).toContain('1 commands')
    expect(details.text()).toContain('team-chat')
  })

  it('toggle plugin enabled calls PATCH', async () => {
    apiMocks.patchPlugin.mockResolvedValue({ ...slackPlugin, enabled: false })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="plugin-toggle-pl-1"]').setValue(false)
    await flushPromises()
    expect(apiMocks.patchPlugin).toHaveBeenCalledWith('pl-1', { enabled: false })
  })

  it('clicking Update posts /update and clears the badge on success', async () => {
    apiMocks.updatePlugin.mockResolvedValue({
      ...slackPlugin,
      installed_version: '1.3.0',
      latest_available_version: '1.3.0',
      update_available: false,
    })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="plugin-update-pl-1"]').trigger('click')
    await flushPromises()
    expect(apiMocks.updatePlugin).toHaveBeenCalledWith('pl-1')
    expect(wrapper.find('[data-testid="plugin-update-badge-pl-1"]').exists()).toBe(false)
  })

  it('install-from-marketplace dialog opens and submits POST', async () => {
    apiMocks.fetchMarketplaces.mockResolvedValue([
      { id: 'mp-1', name: 'acme-public', enabled: true, source_type: 'github', source_url: 'acme/plugins', ref: null, has_auth_token: false, predefined: false, last_synced_at: null, last_sync_status: 'ok', last_sync_error: null, plugin_count: 1, created_at: null, updated_at: null },
    ])
    apiMocks.fetchMarketplacePlugins.mockResolvedValue([
      { name: 'slack-toolkit', source: { source: 'github', repo: 'acme/slack-toolkit' }, version: '1.2.0', available_versions: ['1.2.0', '1.3.0'], skills: ['post-message'], mcp_servers: ['slack'] },
    ])
    apiMocks.installPlugin.mockResolvedValue({ ...slackPlugin })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="plugin-install-marketplace"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="plugin-marketplace-select"]').setValue('mp-1')
    await flushPromises()
    await wrapper.find('[data-testid="plugin-marketplace-plugin-select"]').setValue('slack-toolkit')
    await flushPromises()
    await wrapper.find('[data-testid="plugin-marketplace-confirm"]').trigger('click')
    await flushPromises()
    expect(apiMocks.installPlugin).toHaveBeenCalledWith({
      marketplace_id: 'mp-1',
      plugin_name: 'slack-toolkit',
      version: '1.2.0',
    })
  })

  it('marketplace dialog disables Install for unsupported plugin', async () => {
    apiMocks.fetchMarketplaces.mockResolvedValue([
      { id: 'mp-1', name: 'acme-public', enabled: true, source_type: 'github', source_url: 'acme/plugins', ref: null, has_auth_token: false, predefined: false, last_synced_at: null, last_sync_status: 'ok', last_sync_error: null, plugin_count: 1, created_at: null, updated_at: null },
    ])
    apiMocks.fetchMarketplacePlugins.mockResolvedValue([
      { name: 'npm-plugin', source: { source: 'npm', package: 'x' }, version: '1.0.0', unsupported: true },
    ])
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="plugin-install-marketplace"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="plugin-marketplace-select"]').setValue('mp-1')
    await flushPromises()
    await wrapper.find('[data-testid="plugin-marketplace-plugin-select"]').setValue('npm-plugin')
    await flushPromises()
    expect(wrapper.find('[data-testid="plugin-marketplace-unsupported"]').exists()).toBe(true)
    const confirm = wrapper.find('[data-testid="plugin-marketplace-confirm"]').element as HTMLButtonElement
    expect(confirm.disabled).toBe(true)
  })

  it('manual install dialog submits POST with direct source', async () => {
    apiMocks.fetchCredentials.mockResolvedValue([])
    apiMocks.installPlugin.mockResolvedValue({ ...noUpdatePlugin })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="plugin-install-manual"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="plugin-manual-source-url"]').setValue('acme/research-pack')
    await wrapper.find('[data-testid="plugin-manual-ref"]').setValue('v0.5.0')
    await wrapper.find('[data-testid="plugin-manual-confirm"]').trigger('click')
    await flushPromises()
    expect(apiMocks.installPlugin).toHaveBeenCalledWith({
      source_type: 'github',
      source_url: 'acme/research-pack',
      ref: 'v0.5.0',
      auth_token: null,
    })
  })

  it('manual install error surfaces in dialog and dialog stays open', async () => {
    apiMocks.fetchCredentials.mockResolvedValue([])
    apiMocks.installPlugin.mockRejectedValue(new Error('Invalid plugin source'))
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="plugin-install-manual"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="plugin-manual-source-url"]').setValue('bad/source')
    await wrapper.find('[data-testid="plugin-manual-confirm"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="plugin-manual-error"]').text()).toContain('Invalid plugin source')
    expect(wrapper.find('[data-testid="plugin-manual-dialog"]').exists()).toBe(true)
  })
})
