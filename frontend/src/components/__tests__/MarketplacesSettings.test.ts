import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import MarketplacesSettings from '../settings/MarketplacesSettings.vue'

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const apiMocks = {
  fetchMarketplaces: vi.fn(),
  createMarketplace: vi.fn(),
  patchMarketplace: vi.fn(),
  deleteMarketplace: vi.fn(),
  resyncMarketplace: vi.fn(),
  fetchCredentials: vi.fn(),
}

vi.mock('../../composables/useApi', () => ({
  fetchMarketplaces: (...args: unknown[]) => apiMocks.fetchMarketplaces(...args),
  createMarketplace: (...args: unknown[]) => apiMocks.createMarketplace(...args),
  patchMarketplace: (...args: unknown[]) => apiMocks.patchMarketplace(...args),
  deleteMarketplace: (...args: unknown[]) => apiMocks.deleteMarketplace(...args),
  resyncMarketplace: (...args: unknown[]) => apiMocks.resyncMarketplace(...args),
  fetchCredentials: (...args: unknown[]) => apiMocks.fetchCredentials(...args),
}))

const anthropicRow = {
  id: 'mp-1',
  name: 'anthropics/claude-plugins-official',
  source_type: 'github' as const,
  source_url: 'anthropics/claude-plugins-official',
  ref: null,
  has_auth_token: false,
  enabled: false,
  predefined: true,
  last_synced_at: null,
  last_sync_status: null,
  last_sync_error: null,
  plugin_count: 0,
  created_at: null,
  updated_at: null,
}

const customRow = {
  id: 'mp-2',
  name: 'acme-public',
  source_type: 'http' as const,
  source_url: 'https://litellm.example/marketplace.json',
  ref: null,
  has_auth_token: false,
  enabled: true,
  predefined: false,
  last_synced_at: '2026-06-01T00:00:00Z',
  last_sync_status: 'ok' as const,
  last_sync_error: null,
  plugin_count: 3,
  created_at: null,
  updated_at: null,
}

async function mountComponent() {
  apiMocks.fetchMarketplaces.mockResolvedValue([anthropicRow, customRow])
  apiMocks.fetchCredentials.mockResolvedValue([])
  const wrapper = mount(MarketplacesSettings)
  await flushPromises()
  return wrapper
}

describe('MarketplacesSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('lists marketplaces with predefined badge and sync ok badge', async () => {
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="marketplace-row-mp-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="marketplace-row-mp-2"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="marketplace-predefined-badge"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('anthropics/claude-plugins-official')
    expect(wrapper.text()).toContain('3 plugins')
  })

  it('Remove button is disabled for predefined rows', async () => {
    const wrapper = await mountComponent()
    const removeBtn = wrapper.find('[data-testid="marketplace-delete-mp-1"]').element as HTMLButtonElement
    expect(removeBtn.disabled).toBe(true)
    const removeBtn2 = wrapper.find('[data-testid="marketplace-delete-mp-2"]').element as HTMLButtonElement
    expect(removeBtn2.disabled).toBe(false)
  })

  it('toggle predefined row calls PATCH with enabled true', async () => {
    apiMocks.patchMarketplace.mockResolvedValue({ ...anthropicRow, enabled: true })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="marketplace-toggle-mp-1"]').setValue(true)
    await flushPromises()
    expect(apiMocks.patchMarketplace).toHaveBeenCalledWith('mp-1', { enabled: true })
  })

  it('opens add form and submits POST', async () => {
    apiMocks.createMarketplace.mockResolvedValue({ ...customRow, id: 'mp-3', name: 'new-one' })
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="marketplace-add"]').trigger('click')
    expect(wrapper.find('[data-testid="marketplace-form"]').exists()).toBe(true)
    await wrapper.find('[data-testid="marketplace-name-input"]').setValue('new-one')
    await wrapper.find('[data-testid="marketplace-source-http"]').setValue(true)
    await wrapper.find('[data-testid="marketplace-source-url-input"]').setValue('https://example.com/marketplace.json')
    await wrapper.find('[data-testid="marketplace-save"]').trigger('click')
    await flushPromises()
    expect(apiMocks.createMarketplace).toHaveBeenCalledWith(expect.objectContaining({
      name: 'new-one',
      source_type: 'http',
      source_url: 'https://example.com/marketplace.json',
    }))
  })

  it('Resync calls API and shows loading state', async () => {
    apiMocks.resyncMarketplace.mockResolvedValue(undefined)
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="marketplace-resync-mp-2"]').trigger('click')
    expect(apiMocks.resyncMarketplace).toHaveBeenCalledWith('mp-2')
  })

  it('shows form error and toast on duplicate name', async () => {
    apiMocks.createMarketplace.mockRejectedValue(new Error('Marketplace name already exists'))
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="marketplace-add"]').trigger('click')
    await wrapper.find('[data-testid="marketplace-name-input"]').setValue('dupe')
    await wrapper.find('[data-testid="marketplace-source-url-input"]').setValue('dupe/repo')
    await wrapper.find('[data-testid="marketplace-save"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="marketplace-form-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="marketplace-form"]').exists()).toBe(true)
  })

  it('shows sync error message when last_sync_status is error', async () => {
    apiMocks.fetchMarketplaces.mockResolvedValue([{
      ...customRow,
      last_sync_status: 'error',
      last_sync_error: 'HTTP 401 from upstream',
    }])
    apiMocks.fetchCredentials.mockResolvedValue([])
    const wrapper = mount(MarketplacesSettings)
    await flushPromises()
    expect(wrapper.find('[data-testid="marketplace-sync-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="marketplace-sync-error-message"]').text()).toContain('HTTP 401')
  })
})
