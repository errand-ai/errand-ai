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

  it('renders provider cards after loading', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: true, connected: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-card-google_drive"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-card-onedrive"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Google Drive')
    expect(wrapper.text()).toContain('OneDrive')
  })

  it('shows Connect button when available but not connected', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: true, connected: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    expect(wrapper.find('[data-testid="cloud-connect-google_drive"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cloud-connect-google_drive"]').text()).toBe('Connect')
  })

  it('shows connected user info and Disconnect button when connected', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: {
        available: true,
        connected: true,
        user_email: 'user@gmail.com',
        user_name: 'Test User',
      },
      onedrive: { available: true, connected: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-google_drive"]')
    expect(card.find('[data-testid="cloud-user-google_drive"]').text()).toContain('Test User')
    expect(card.find('[data-testid="cloud-user-google_drive"]').text()).toContain('user@gmail.com')
    expect(card.find('[data-testid="cloud-disconnect-google_drive"]').exists()).toBe(true)
    expect(card.find('[data-testid="cloud-connect-google_drive"]').exists()).toBe(false)
  })

  it('shows "MCP server URL not set" when not available and no MCP URL', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false, mode: null, mcp_configured: false },
      onedrive: { available: false, connected: false, mode: null, mcp_configured: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-google_drive"]')
    expect(card.classes()).toContain('opacity-60')
    expect(card.text()).toContain('MCP server URL not set')
    expect(card.find('[data-testid="cloud-connect-google_drive"]').exists()).toBe(false)
  })

  it('shows "configure credentials or connect to errand cloud" when MCP configured but no auth', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false, mode: null, mcp_configured: true },
      onedrive: { available: false, connected: false, mode: null, mcp_configured: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-google_drive"]')
    expect(card.text()).toContain('Configure credentials or connect to errand cloud')
  })

  it('shows Connect button for cloud mode provider', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false, mode: 'cloud', mcp_configured: true },
      onedrive: { available: false, connected: false, mode: null, mcp_configured: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-google_drive"]')
    expect(card.find('[data-testid="cloud-connect-google_drive"]').exists()).toBe(true)
    expect(card.find('[data-testid="cloud-connect-google_drive"]').text()).toBe('Connect')
  })

  it('disconnect calls API and refreshes status', async () => {
    mockFetchCloudStorageStatus
      .mockResolvedValueOnce({
        google_drive: {
          available: true,
          connected: true,
          user_email: 'user@gmail.com',
          user_name: 'Test User',
        },
        onedrive: { available: true, connected: false },
      })
      .mockResolvedValueOnce({
        google_drive: { available: true, connected: false },
        onedrive: { available: true, connected: false },
      })

    mockDisconnectCloudStorage.mockResolvedValue(undefined)

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    await wrapper.find('[data-testid="cloud-disconnect-google_drive"]').trigger('click')
    await flushPromises()

    expect(mockDisconnectCloudStorage).toHaveBeenCalledWith('google_drive')
    expect(mockFetchCloudStorageStatus).toHaveBeenCalledTimes(2)
  })

  it('connect button opens OAuth popup', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: true, connected: false },
    })
    mockAuthorizeCloudStorage.mockResolvedValue({
      redirect_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
    })

    const mockPopup = { closed: false }
    vi.spyOn(window, 'open').mockReturnValue(mockPopup as unknown as Window)

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    await wrapper.find('[data-testid="cloud-connect-google_drive"]').trigger('click')
    await flushPromises()

    expect(mockAuthorizeCloudStorage).toHaveBeenCalledWith('google_drive')
    expect(window.open).toHaveBeenCalledWith(
      'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
      'cloud-storage-auth',
      expect.stringContaining('width=500'),
    )

    vi.restoreAllMocks()
  })
})
