import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PlatformCredentialForm from '../settings/PlatformCredentialForm.vue'

vi.mock('../../composables/useApi', () => ({
  fetchTaskProfiles: vi.fn(),
}))

import { fetchTaskProfiles } from '../../composables/useApi'

const githubSchema = [
  {
    key: 'auth_mode',
    label: 'Auth Mode',
    type: 'select',
    required: true,
    options: [
      { value: 'pat', label: 'Personal Access Token' },
      { value: 'app', label: 'GitHub App' },
    ],
  },
  { key: 'personal_access_token', label: 'Personal Access Token', type: 'password', required: true, auth_mode: 'pat' },
  { key: 'app_id', label: 'App ID', type: 'text', required: true, auth_mode: 'app' },
  { key: 'private_key', label: 'Private Key (PEM)', type: 'textarea', required: true, auth_mode: 'app' },
  { key: 'installation_id', label: 'Installation ID', type: 'text', required: true, auth_mode: 'app' },
]

const simpleSchema = [
  { key: 'api_key', label: 'API Key', type: 'password', required: true },
  { key: 'api_secret', label: 'API Secret', type: 'password', required: true },
]

const emailSchema = [
  { key: 'imap_host', label: 'IMAP Server', type: 'text', required: true },
  { key: 'email_profile', label: 'Task Profile', type: 'profile_select', required: true },
  { key: 'poll_interval', label: 'Poll Interval (seconds)', type: 'text', required: false, help_text: 'Minimum 60. Reduced when IMAP IDLE is supported.' },
]

beforeEach(() => {
  vi.mocked(fetchTaskProfiles).mockReset()
})

describe('PlatformCredentialForm', () => {
  it('renders password inputs for simple schema', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: simpleSchema, saving: false },
    })

    expect(wrapper.find('[data-testid="cred-input-api_key"]').attributes('type')).toBe('password')
    expect(wrapper.find('[data-testid="cred-input-api_secret"]').attributes('type')).toBe('password')
  })

  it('does not render a toggle for schemas without a select field', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: simpleSchema, saving: false },
    })

    expect(wrapper.find('[data-testid="cred-input-auth_mode"]').exists()).toBe(false)
  })

  it('renders toggle buttons for select type fields', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    const toggle = wrapper.find('[data-testid="cred-input-auth_mode"]')
    expect(toggle.exists()).toBe(true)
    const buttons = toggle.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0].text()).toBe('Personal Access Token')
    expect(buttons[1].text()).toBe('GitHub App')
  })

  it('highlights the active toggle option', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    const patButton = wrapper.find('[data-testid="cred-toggle-pat"]')
    const appButton = wrapper.find('[data-testid="cred-toggle-app"]')
    expect(patButton.classes()).toContain('bg-blue-600')
    expect(appButton.classes()).not.toContain('bg-blue-600')
  })

  it('shows PAT fields when auth_mode is pat (default)', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    // PAT field visible
    expect(wrapper.find('[data-testid="cred-input-personal_access_token"]').exists()).toBe(true)
    // App fields hidden
    expect(wrapper.find('[data-testid="cred-input-app_id"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="cred-input-private_key"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="cred-input-installation_id"]').exists()).toBe(false)
  })

  it('shows App fields when toggle is clicked to app', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    await wrapper.find('[data-testid="cred-toggle-app"]').trigger('click')

    // App fields visible
    expect(wrapper.find('[data-testid="cred-input-app_id"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cred-input-private_key"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cred-input-installation_id"]').exists()).toBe(true)
    // PAT field hidden
    expect(wrapper.find('[data-testid="cred-input-personal_access_token"]').exists()).toBe(false)
  })

  it('switches highlight when toggling between modes', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    await wrapper.find('[data-testid="cred-toggle-app"]').trigger('click')

    const patButton = wrapper.find('[data-testid="cred-toggle-pat"]')
    const appButton = wrapper.find('[data-testid="cred-toggle-app"]')
    expect(appButton.classes()).toContain('bg-blue-600')
    expect(patButton.classes()).not.toContain('bg-blue-600')
  })

  it('renders textarea for textarea type fields', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    await wrapper.find('[data-testid="cred-toggle-app"]').trigger('click')

    const textarea = wrapper.find('[data-testid="cred-input-private_key"]')
    expect(textarea.element.tagName).toBe('TEXTAREA')
  })

  it('renders text inputs for text type fields', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    await wrapper.find('[data-testid="cred-toggle-app"]').trigger('click')

    expect(wrapper.find('[data-testid="cred-input-app_id"]').attributes('type')).toBe('text')
    expect(wrapper.find('[data-testid="cred-input-installation_id"]').attributes('type')).toBe('text')
  })

  it('only submits visible fields plus mode', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    // Default is PAT mode
    const patInput = wrapper.find('[data-testid="cred-input-personal_access_token"]')
    await patInput.setValue('ghp_test_token')

    await wrapper.find('[data-testid="credential-form"]').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect(emitted).toHaveLength(1)
    const creds = emitted![0][0] as Record<string, string>
    expect(creds.auth_mode).toBe('pat')
    expect(creds.personal_access_token).toBe('ghp_test_token')
    // App fields should not be present
    expect(creds).not.toHaveProperty('app_id')
    expect(creds).not.toHaveProperty('private_key')
    expect(creds).not.toHaveProperty('installation_id')
  })

  it('submits app fields when auth_mode is app', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    await wrapper.find('[data-testid="cred-toggle-app"]').trigger('click')
    await wrapper.find('[data-testid="cred-input-app_id"]').setValue('12345')
    await wrapper.find('[data-testid="cred-input-private_key"]').setValue('-----BEGIN RSA PRIVATE KEY-----')
    await wrapper.find('[data-testid="cred-input-installation_id"]').setValue('67890')

    await wrapper.find('[data-testid="credential-form"]').trigger('submit')

    const emitted = wrapper.emitted('save')
    expect(emitted).toHaveLength(1)
    const creds = emitted![0][0] as Record<string, string>
    expect(creds.auth_mode).toBe('app')
    expect(creds.app_id).toBe('12345')
    expect(creds.private_key).toBe('-----BEGIN RSA PRIVATE KEY-----')
    expect(creds.installation_id).toBe('67890')
    expect(creds).not.toHaveProperty('personal_access_token')
  })

  it('disables submit button when saving', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: simpleSchema, saving: true },
    })

    const button = wrapper.find('[data-testid="credential-save"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toBe('Testing...')
  })

  // --- Task 7.6: profile_select field type tests ---

  it('renders a <select> dropdown for profile_select fields', async () => {
    vi.mocked(fetchTaskProfiles).mockResolvedValue([])

    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: emailSchema, saving: false },
    })
    await flushPromises()

    const select = wrapper.find('[data-testid="cred-input-email_profile"]')
    expect(select.exists()).toBe(true)
    expect(select.element.tagName).toBe('SELECT')
  })

  it('shows "No task profiles configured" when profiles list is empty', async () => {
    vi.mocked(fetchTaskProfiles).mockResolvedValue([])

    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: emailSchema, saving: false },
    })
    await flushPromises()

    const select = wrapper.find('[data-testid="cred-input-email_profile"]')
    const options = select.findAll('option')
    expect(options).toHaveLength(1)
    expect(options[0].text()).toContain('No task profiles configured')
  })

  it('shows profile names when profiles exist', async () => {
    vi.mocked(fetchTaskProfiles).mockResolvedValue([
      { id: 'p1', name: 'Default Profile', description: null, match_rules: null, model: null, system_prompt: null, max_turns: null, reasoning_effort: null, mcp_servers: null, litellm_mcp_servers: null, skill_ids: null, created_at: '', updated_at: '' },
      { id: 'p2', name: 'Email Profile', description: null, match_rules: null, model: null, system_prompt: null, max_turns: null, reasoning_effort: null, mcp_servers: null, litellm_mcp_servers: null, skill_ids: null, created_at: '', updated_at: '' },
    ])

    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: emailSchema, saving: false },
    })
    await flushPromises()

    const select = wrapper.find('[data-testid="cred-input-email_profile"]')
    const options = select.findAll('option')
    // "Select a profile" + 2 profiles
    expect(options).toHaveLength(3)
    expect(options[0].text()).toBe('Select a profile')
    expect(options[1].text()).toBe('Default Profile')
    expect(options[2].text()).toBe('Email Profile')
  })

  it('displays help_text below fields that have it', async () => {
    vi.mocked(fetchTaskProfiles).mockResolvedValue([])

    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: emailSchema, saving: false },
    })
    await flushPromises()

    // poll_interval field has help_text
    const helpText = wrapper.text()
    expect(helpText).toContain('Minimum 60')
  })

  it('profile_select is not treated as a modeField (toggle)', async () => {
    vi.mocked(fetchTaskProfiles).mockResolvedValue([])

    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: emailSchema, saving: false },
    })
    await flushPromises()

    // Should not render as toggle buttons — profile_select type doesn't match modeField filter
    // (modeField is type: 'select' with options, profile_select is type: 'profile_select')
    const buttons = wrapper.findAll('button[data-testid^="cred-toggle-"]')
    expect(buttons).toHaveLength(0)

    // The profile_select should still be visible as a regular field
    const select = wrapper.find('[data-testid="cred-input-email_profile"]')
    expect(select.exists()).toBe(true)
  })
})
