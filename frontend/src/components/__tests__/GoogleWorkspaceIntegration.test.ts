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
        // Full Workspace scope set — necessary for the "Disconnect" path now
        // that the UI gates on per-badge scope coverage, not just the boolean.
        granted_scopes: [
          'openid', 'email', 'profile',
          'https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/calendar',
          'https://www.googleapis.com/auth/spreadsheets',
          'https://www.googleapis.com/auth/documents',
          'https://www.googleapis.com/auth/chat.messages',
          'https://www.googleapis.com/auth/tasks',
          'https://www.googleapis.com/auth/contacts.readonly',
        ],
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

  // --- Per-service badge state derived from granted_scopes ---

  const FULL_WORKSPACE_SCOPES = [
    'openid', 'email', 'profile',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/chat.messages',
    'https://www.googleapis.com/auth/tasks',
    'https://www.googleapis.com/auth/contacts.readonly',
  ]

  const ALL_BADGES = ['drive', 'gmail', 'calendar', 'sheets', 'docs', 'chat', 'tasks', 'contacts']

  function badgeActive(wrapper: ReturnType<typeof mount>, key: string): boolean {
    return wrapper.find(`[data-testid="google-service-${key}"]`).attributes('data-active') === 'true'
  }

  it('renders every badge active when full Workspace scope set is granted', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: {
        available: true,
        connected: true,
        user_email: 'user@gmail.com',
        reauth_required: false,
        granted_scopes: FULL_WORKSPACE_SCOPES,
      },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    for (const key of ALL_BADGES) {
      expect(badgeActive(wrapper, key)).toBe(true)
    }
    expect(wrapper.find('[data-testid="google-workspace-reauth-warning"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="google-workspace-disconnect"]').exists()).toBe(true)
  })

  it('keeps non-Drive badges muted when only auth/drive is granted', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: {
        available: true,
        connected: true,
        user_email: 'user@gmail.com',
        reauth_required: true,
        granted_scopes: ['openid', 'https://www.googleapis.com/auth/drive'],
      },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    expect(badgeActive(wrapper, 'drive')).toBe(true)
    for (const key of ALL_BADGES.filter(k => k !== 'drive')) {
      expect(badgeActive(wrapper, key)).toBe(false)
    }
    // Warning visible because the other services' scopes are missing.
    expect(wrapper.find('[data-testid="google-workspace-reauth-warning"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="google-workspace-reauthorize"]').exists()).toBe(true)
  })

  it('renders partial-grant set with warning still visible', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: {
        available: true,
        connected: true,
        user_email: 'user@gmail.com',
        // Backend reports false because the required set is satisfied for
        // its check, but the UI still finds gaps via the per-badge mapping.
        reauth_required: false,
        granted_scopes: [
          'https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/calendar',
        ],
      },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    for (const key of ['drive', 'gmail', 'calendar']) {
      expect(badgeActive(wrapper, key)).toBe(true)
    }
    for (const key of ['sheets', 'docs', 'chat', 'tasks', 'contacts']) {
      expect(badgeActive(wrapper, key)).toBe(false)
    }
    // Tightened warning condition: any missing badge → warning shown.
    expect(wrapper.find('[data-testid="google-workspace-reauth-warning"]').exists()).toBe(true)
  })

  it('renders all badges muted when not connected', async () => {
    mockFetchCloudStorageStatus.mockResolvedValue({
      google_drive: { available: true, connected: false },
      onedrive: { available: false, connected: false },
    })

    const wrapper = mount(GoogleWorkspaceIntegration)
    await flushPromises()

    for (const key of ALL_BADGES) {
      expect(badgeActive(wrapper, key)).toBe(false)
    }
    expect(wrapper.find('[data-testid="google-workspace-reauth-warning"]').exists()).toBe(false)
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

    // connect() starts a 500 ms poller and a 10-min timeout that don't clear
    // until the popup closes. Always unmount in finally so vitest doesn't
    // leak active timers between tests.
    const wrapper = mount(GoogleWorkspaceIntegration)
    try {
      await flushPromises()

      await wrapper.find('[data-testid="google-workspace-connect"]').trigger('click')
      await flushPromises()

      expect(mockAuthorizeCloudStorage).toHaveBeenCalledWith('google_drive')
      expect(window.open).toHaveBeenCalledWith(
        'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
        'google-workspace-auth',
        expect.stringContaining('width=500'),
      )
    } finally {
      wrapper.unmount()
      vi.restoreAllMocks()
    }
  })

  it('disconnect calls API and refreshes status', async () => {
    mockFetchCloudStorageStatus
      .mockResolvedValueOnce({
        google_drive: {
          available: true,
          connected: true,
          user_email: 'user@gmail.com',
          reauth_required: false,
          granted_scopes: FULL_WORKSPACE_SCOPES,
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
