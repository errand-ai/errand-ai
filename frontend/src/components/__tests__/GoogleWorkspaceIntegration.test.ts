import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GoogleWorkspaceIntegration from '../settings/GoogleWorkspaceIntegration.vue'

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

const SERVICE_KEYS = ['drive', 'gmail', 'calendar', 'sheets', 'docs', 'chat', 'tasks', 'contacts']

describe('GoogleWorkspaceIntegration', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows loading state initially', () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    expect(wrapper.text()).toContain('Loading...')
  })

  it('renders all eight service badges', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    for (const key of SERVICE_KEYS) {
      expect(wrapper.find(`[data-testid="google-service-${key}"]`).exists()).toBe(true)
    }
  })

  it('shows Connect button when available but not connected', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    expect(wrapper.find('[data-testid="google-workspace-connect"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="google-workspace-disconnect"]').exists()).toBe(false)
  })

  it('shows Disconnect button and user info when connected with current scopes', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: {
        available: true,
        connected: true,
        user_email: 'user@gmail.com',
        user_name: 'Test User',
        reauth_required: false,
      },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    expect(wrapper.find('[data-testid="google-workspace-disconnect"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="google-workspace-reauthorize"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="google-workspace-user"]').text()).toContain('Test User')
    expect(wrapper.find('[data-testid="google-workspace-user"]').text()).toContain('user@gmail.com')
  })

  it('shows Re-authorize button and warning when reauth_required', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: {
        available: true,
        connected: true,
        user_email: 'user@gmail.com',
        reauth_required: true,
      },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    expect(wrapper.find('[data-testid="google-workspace-reauthorize"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="google-workspace-disconnect"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="google-workspace-reauth-warning"]').exists()).toBe(true)
  })

  it('connect button opens OAuth popup', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: false, connected: false },
    })
    mockAuthorizeCloudStorage.mockResolvedValue({
      redirect_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
    })

    const mockPopup = { closed: false }
    vi.spyOn(window, 'open').mockReturnValue(mockPopup as unknown as Window)

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    await wrapper.find('[data-testid="google-workspace-connect"]').trigger('click')
    await flushPromises()

    expect(mockAuthorizeCloudStorage).toHaveBeenCalledWith('google_drive')
    expect(window.open).toHaveBeenCalledWith(
      'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
      'google-workspace-auth',
      expect.stringContaining('width=500'),
    )

    vi.restoreAllMocks()
  })

  it('disconnect calls API and refreshes status', async () => {
    mockFetchCloudStorageStatus
      .mockResolvedValueOnce({
        google_drive: {
          available: true,
          connected: true,
          user_email: 'user@gmail.com',
          reauth_required: false,
        },
        onedrive: { available: false, connected: false },
      })
      .mockResolvedValueOnce({
        google_drive: { available: true, connected: false },
        onedrive: { available: false, connected: false },
      })

    mockDisconnectCloudStorage.mockResolvedValue(undefined)

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    await wrapper.find('[data-testid="google-workspace-disconnect"]').trigger('click')
    await flushPromises()

    expect(mockDisconnectCloudStorage).toHaveBeenCalledWith('google_drive')
    expect(mockFetchCloudStorageStatus).toHaveBeenCalledTimes(2)
  })
})
