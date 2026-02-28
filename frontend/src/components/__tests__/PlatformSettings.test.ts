import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PlatformSettings from '../settings/PlatformSettings.vue'

// Mock vue-sonner
vi.mock('vue-sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockPlatforms = [
  {
    id: 'twitter',
    label: 'Twitter / X',
    capabilities: ['post', 'schedule'],
    credential_schema: [
      { key: 'api_key', label: 'API Key', type: 'password', required: true },
      { key: 'api_secret', label: 'API Secret', type: 'password', required: true },
    ],
    status: 'disconnected',
    last_verified_at: null,
  },
  {
    id: 'linkedin',
    label: 'LinkedIn',
    capabilities: ['post'],
    credential_schema: [
      { key: 'access_token', label: 'Access Token', type: 'password', required: true },
    ],
    status: 'connected',
    last_verified_at: '2026-01-15T10:30:00Z',
  },
  {
    id: 'email',
    label: 'Email',
    capabilities: ['email'],
    credential_schema: [
      { key: 'imap_host', label: 'IMAP Server', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
      { key: 'poll_interval', label: 'Poll Interval', type: 'text', required: false, editable: true },
      { key: 'authorized_recipients', label: 'Authorized Recipients', type: 'textarea', required: false, editable: true },
    ],
    status: 'connected',
    last_verified_at: '2026-02-01T08:00:00Z',
  },
]

const mockFetchPlatforms = vi.fn()
const mockSavePlatformCredentials = vi.fn()
const mockDeletePlatformCredentials = vi.fn()
const mockVerifyPlatformCredentials = vi.fn()
const mockPatchPlatformCredentials = vi.fn()
const mockFetchPlatformCredentialStatus = vi.fn()
const mockFetchTaskProfiles = vi.fn()

vi.mock('../../composables/useApi', () => ({
  fetchPlatforms: (...args: unknown[]) => mockFetchPlatforms(...args),
  savePlatformCredentials: (...args: unknown[]) => mockSavePlatformCredentials(...args),
  deletePlatformCredentials: (...args: unknown[]) => mockDeletePlatformCredentials(...args),
  verifyPlatformCredentials: (...args: unknown[]) => mockVerifyPlatformCredentials(...args),
  patchPlatformCredentials: (...args: unknown[]) => mockPatchPlatformCredentials(...args),
  fetchPlatformCredentialStatus: (...args: unknown[]) => mockFetchPlatformCredentialStatus(...args),
  fetchTaskProfiles: (...args: unknown[]) => mockFetchTaskProfiles(...args),
}))

describe('PlatformSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockFetchPlatforms.mockResolvedValue([...mockPlatforms])
  })

  it('renders platform list after loading', async () => {
    const wrapper = mount(PlatformSettings)
    expect(wrapper.text()).toContain('Loading platforms...')

    await flushPromises()

    expect(wrapper.find('[data-testid="platform-card-twitter"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="platform-card-linkedin"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Twitter / X')
    expect(wrapper.text()).toContain('LinkedIn')
  })

  it('shows connection status indicators', async () => {
    const wrapper = mount(PlatformSettings)
    await flushPromises()

    const twitterStatus = wrapper.find('[data-testid="platform-status-twitter"]')
    expect(twitterStatus.classes()).toContain('bg-gray-400')

    const linkedinStatus = wrapper.find('[data-testid="platform-status-linkedin"]')
    expect(linkedinStatus.classes()).toContain('bg-green-500')
  })

  it('shows last_verified_at for connected platforms', async () => {
    const wrapper = mount(PlatformSettings)
    await flushPromises()

    expect(wrapper.find('[data-testid="platform-verified-at-linkedin"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="platform-verified-at-twitter"]').exists()).toBe(false)
  })

  it('shows credential form for disconnected platforms only', async () => {
    const wrapper = mount(PlatformSettings)
    await flushPromises()

    const twitterCard = wrapper.find('[data-testid="platform-card-twitter"]')
    expect(twitterCard.find('[data-testid="credential-form"]').exists()).toBe(true)

    const linkedinCard = wrapper.find('[data-testid="platform-card-linkedin"]')
    expect(linkedinCard.find('[data-testid="credential-form"]').exists()).toBe(false)
  })

  it('shows verify and disconnect buttons for connected platforms', async () => {
    const wrapper = mount(PlatformSettings)
    await flushPromises()

    expect(wrapper.find('[data-testid="platform-verify-linkedin"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="platform-disconnect-linkedin"]').exists()).toBe(true)

    expect(wrapper.find('[data-testid="platform-verify-twitter"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="platform-disconnect-twitter"]').exists()).toBe(false)
  })

  it('saves credentials via form submission', async () => {
    mockSavePlatformCredentials.mockResolvedValue({
      ...mockPlatforms[0],
      status: 'connected',
      last_verified_at: '2026-02-17T12:00:00Z',
    })

    const wrapper = mount(PlatformSettings)
    await flushPromises()

    const form = wrapper.find('[data-testid="credential-form"]')
    const inputs = form.findAll('input[type="password"]')
    await inputs[0].setValue('key123')
    await inputs[1].setValue('secret456')

    await form.trigger('submit')
    await flushPromises()

    expect(mockSavePlatformCredentials).toHaveBeenCalledWith('twitter', {
      api_key: 'key123',
      api_secret: 'secret456',
    })
  })

  it('verifies credentials when verify button clicked', async () => {
    mockVerifyPlatformCredentials.mockResolvedValue({
      ...mockPlatforms[1],
      status: 'connected',
      last_verified_at: '2026-02-17T12:00:00Z',
    })

    const wrapper = mount(PlatformSettings)
    await flushPromises()

    await wrapper.find('[data-testid="platform-verify-linkedin"]').trigger('click')
    await flushPromises()

    expect(mockVerifyPlatformCredentials).toHaveBeenCalledWith('linkedin')
  })

  it('shows error state when loading fails', async () => {
    mockFetchPlatforms.mockRejectedValue(new Error('Network error'))

    const wrapper = mount(PlatformSettings)
    await flushPromises()

    expect(wrapper.text()).toContain('Failed to load platforms.')
  })

  it('displays capabilities as badges', async () => {
    const wrapper = mount(PlatformSettings)
    await flushPromises()

    const twitterCard = wrapper.find('[data-testid="platform-card-twitter"]')
    expect(twitterCard.text()).toContain('post')
    expect(twitterCard.text()).toContain('schedule')
  })

  // --- Edit mode tests ---

  it('shows Edit button for connected platform with editable fields', async () => {
    const wrapper = mount(PlatformSettings)
    await flushPromises()

    // Email has editable fields → Edit button shown
    expect(wrapper.find('[data-testid="platform-edit-email"]').exists()).toBe(true)
    // LinkedIn has no editable fields → no Edit button
    expect(wrapper.find('[data-testid="platform-edit-linkedin"]').exists()).toBe(false)
    // Twitter is disconnected → no Edit button
    expect(wrapper.find('[data-testid="platform-edit-twitter"]').exists()).toBe(false)
  })

  it('opens edit form with pre-populated values when Edit clicked', async () => {
    mockFetchPlatformCredentialStatus.mockResolvedValue({
      platform_id: 'email',
      status: 'connected',
      field_values: { poll_interval: '120', authorized_recipients: 'user@test.com' },
    })

    const wrapper = mount(PlatformSettings)
    await flushPromises()

    await wrapper.find('[data-testid="platform-edit-email"]').trigger('click')
    await flushPromises()

    expect(mockFetchPlatformCredentialStatus).toHaveBeenCalledWith('email')
    expect(wrapper.find('[data-testid="platform-edit-form-email"]').exists()).toBe(true)

    // The edit form should only show editable fields (poll_interval, authorized_recipients)
    // and NOT show non-editable fields (imap_host, password)
    const editForm = wrapper.find('[data-testid="platform-edit-form-email"]')
    expect(editForm.find('[data-testid="cred-input-poll_interval"]').exists()).toBe(true)
    expect(editForm.find('[data-testid="cred-input-authorized_recipients"]').exists()).toBe(true)
    expect(editForm.find('[data-testid="cred-input-imap_host"]').exists()).toBe(false)
    expect(editForm.find('[data-testid="cred-input-password"]').exists()).toBe(false)
  })

  it('pre-populates edit form fields with current values', async () => {
    mockFetchPlatformCredentialStatus.mockResolvedValue({
      platform_id: 'email',
      status: 'connected',
      field_values: { poll_interval: '120', authorized_recipients: 'user@test.com' },
    })

    const wrapper = mount(PlatformSettings)
    await flushPromises()

    await wrapper.find('[data-testid="platform-edit-email"]').trigger('click')
    await flushPromises()

    const editForm = wrapper.find('[data-testid="platform-edit-form-email"]')
    const pollInput = editForm.find('[data-testid="cred-input-poll_interval"]')
    expect((pollInput.element as HTMLInputElement).value).toBe('120')

    const recipientsInput = editForm.find('[data-testid="cred-input-authorized_recipients"]')
    expect((recipientsInput.element as HTMLTextAreaElement).value).toBe('user@test.com')
  })

  it('calls PATCH endpoint on save and shows toast', async () => {
    mockFetchPlatformCredentialStatus.mockResolvedValue({
      platform_id: 'email',
      status: 'connected',
      field_values: { poll_interval: '60', authorized_recipients: '' },
    })
    mockPatchPlatformCredentials.mockResolvedValue({
      status: 'connected',
      last_verified_at: '2026-02-01T08:00:00Z',
    })

    const wrapper = mount(PlatformSettings)
    await flushPromises()

    await wrapper.find('[data-testid="platform-edit-email"]').trigger('click')
    await flushPromises()

    // Change poll_interval
    const editForm = wrapper.find('[data-testid="platform-edit-form-email"]')
    await editForm.find('[data-testid="cred-input-poll_interval"]').setValue('120')
    await editForm.find('[data-testid="credential-form"]').trigger('submit')
    await flushPromises()

    expect(mockPatchPlatformCredentials).toHaveBeenCalledWith('email', {
      poll_interval: '120',
      authorized_recipients: '',
    })

    // Form should close after save
    expect(wrapper.find('[data-testid="platform-edit-form-email"]').exists()).toBe(false)
  })

  it('closes edit form on cancel without calling PATCH', async () => {
    mockFetchPlatformCredentialStatus.mockResolvedValue({
      platform_id: 'email',
      status: 'connected',
      field_values: { poll_interval: '60', authorized_recipients: '' },
    })

    const wrapper = mount(PlatformSettings)
    await flushPromises()

    await wrapper.find('[data-testid="platform-edit-email"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="platform-edit-form-email"]').exists()).toBe(true)

    await wrapper.find('[data-testid="platform-edit-cancel"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="platform-edit-form-email"]').exists()).toBe(false)
    expect(mockPatchPlatformCredentials).not.toHaveBeenCalled()
  })
})
