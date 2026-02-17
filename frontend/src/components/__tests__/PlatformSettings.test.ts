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
]

const mockFetchPlatforms = vi.fn()
const mockSavePlatformCredentials = vi.fn()
const mockDeletePlatformCredentials = vi.fn()
const mockVerifyPlatformCredentials = vi.fn()

vi.mock('../../composables/useApi', () => ({
  fetchPlatforms: (...args: unknown[]) => mockFetchPlatforms(...args),
  savePlatformCredentials: (...args: unknown[]) => mockSavePlatformCredentials(...args),
  deletePlatformCredentials: (...args: unknown[]) => mockDeletePlatformCredentials(...args),
  verifyPlatformCredentials: (...args: unknown[]) => mockVerifyPlatformCredentials(...args),
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
})
