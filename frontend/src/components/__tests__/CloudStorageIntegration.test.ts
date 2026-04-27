import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CloudStorageIntegration from '../settings/CloudStorageIntegration.vue'

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockFetchCloudStorageStatus = vi.fn()
const mockAuthorizeCloudStorage = vi.fn()
const mockDisconnectCloudStorage = vi.fn()

vi.mock('../../composables/useApi', () => ({
  fetchCloudStorageStatus: (...args: unknown[]) => mockFetchCloudStorageStatus(...args),
  authorizeCloudStorage: (...args: unknown[]) => mockAuthorizeCloudStorage(...args),
  disconnectCloudStorage: (...args: unknown[]) => mockDisconnectCloudStorage(...args),
}))

// CloudStorageIntegration now renders OneDrive only — Google Workspace
// (formerly Google Drive) lives in its own dedicated section.
describe('CloudStorageIntegration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows loading state initially', () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    expect(wrapper.text()).toContain('Loading...')
  })

  it('renders only the OneDrive card after loading', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: true },
      onedrive: { available: true, connected: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-card-onedrive"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-card-google_drive"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('OneDrive')
    expect(wrapper.text()).not.toContain('Google Drive')
  })

  it('shows Connect button when OneDrive is available but not connected', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: true, connected: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-connect-onedrive"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-connect-onedrive"]').text()).toBe('Connect')
  })

  it('shows connected user info and Disconnect button when OneDrive is connected', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false },
      onedrive: {
        available: true,
        connected: true,
        user_email: 'user@example.com',
        user_name: 'Test User',
      },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-onedrive"]')
    expect(card.find('[data-testid="cloud-user-onedrive"]').text()).toContain('Test User')
    expect(card.find('[data-testid="cloud-user-onedrive"]').text()).toContain('user@example.com')
    expect(card.find('[data-testid="cloud-disconnect-onedrive"]').exists()).toBe(true)
    expect(card.find('[data-testid="cloud-connect-onedrive"]').exists()).toBe(false)
  })

  it('shows "MCP server URL not set" when OneDrive is unavailable with no MCP URL', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false, mode: null, mcp_configured: true },
      onedrive: { available: false, connected: false, mode: null, mcp_configured: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-onedrive"]')
    expect(card.classes()).toContain('opacity-60')
    expect(card.text()).toContain('MCP server URL not set')
    expect(card.find('[data-testid="cloud-connect-onedrive"]').exists()).toBe(false)
  })

  it('shows "configure credentials or connect to errand cloud" when OneDrive MCP configured but no auth', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false, mode: null, mcp_configured: true },
      onedrive: { available: false, connected: false, mode: null, mcp_configured: true },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-onedrive"]')
    expect(card.text()).toContain('Configure credentials or connect to errand cloud')
  })

  it('disconnect calls API and refreshes status', async () => {
    mockFetchCloudStorageStatus
      .mockResolvedValueOnce({
        google_drive: { available: false, connected: false },
        onedrive: {
          available: true,
          connected: true,
          user_email: 'user@example.com',
          user_name: 'Test User',
        },
      })
      .mockResolvedValueOnce({
        google_drive: { available: false, connected: false },
        onedrive: { available: true, connected: false },
      })

    mockDisconnectCloudStorage.mockResolvedValue(undefined)

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    await wrapper.find('[data-testid="cloud-disconnect-onedrive"]').trigger('click')
    await flushPromises()

    expect(mockDisconnectCloudStorage).toHaveBeenCalledWith('onedrive')
    expect(mockFetchCloudStorageStatus).toHaveBeenCalledTimes(2)
  })

  it('connect button opens OAuth popup', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false },
      onedrive: { available: true, connected: false },
    })
    mockAuthorizeCloudStorage.mockResolvedValue({
      redirect_url: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=test',
    })

    const mockPopup = { closed: false }
    vi.spyOn(window, 'open').mockReturnValue(mockPopup as unknown as Window)

    // connect() starts long-running timers that only clear when the popup
    // closes; unmount in finally so they don't leak between tests.
    const wrapper = mount(CloudStorageIntegration)
    try {
      await flushPromises()

      await wrapper.find('[data-testid="cloud-connect-onedrive"]').trigger('click')
      await flushPromises()

      expect(mockAuthorizeCloudStorage).toHaveBeenCalledWith('onedrive')
      expect(window.open).toHaveBeenCalledWith(
        'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=test',
        'cloud-storage-auth',
        expect.stringContaining('width=500'),
      )
    } finally {
      wrapper.unmount()
      vi.restoreAllMocks()
    }
  })
})
