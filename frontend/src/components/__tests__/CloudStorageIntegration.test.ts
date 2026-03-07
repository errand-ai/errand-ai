import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import CloudStorageIntegration from '../settings/CloudStorageIntegration.vue'

vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockFetchCloudStorageStatus = vi.fn()
const mockDisconnectCloudStorage = vi.fn()

vi.mock('../../composables/useApi', () => ({
  fetchCloudStorageStatus: (...args: unknown[]) => mockFetchCloudStorageStatus(...args),
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

  it('shows greyed-out state when not available', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: false, connected: false },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    const card = wrapper.find('[data-testid="cloud-card-google_drive"]')
    expect(card.classes()).toContain('opacity-60')
    expect(card.text()).toContain('Not configured')
    expect(card.find('[data-testid="cloud-connect-google_drive"]').exists()).toBe(false)
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

  it('connect button navigates to authorize URL', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: true, connected: false },
    })

    // Mock window.location
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { ...originalLocation, href: '' },
    })

    const wrapper = mount(CloudStorageIntegration)
    await flushPromises()

    await wrapper.find('[data-testid="cloud-connect-google_drive"]').trigger('click')

    expect(window.location.href).toBe('/api/integrations/google_drive/authorize')

    // Restore
    Object.defineProperty(window, 'location', {
      writable: true,
      value: originalLocation,
    })
  })
})
