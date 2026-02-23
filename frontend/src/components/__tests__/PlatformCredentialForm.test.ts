import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PlatformCredentialForm from '../settings/PlatformCredentialForm.vue'

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

describe('PlatformCredentialForm', () => {
  it('renders password inputs for simple schema', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: simpleSchema, saving: false },
    })

    expect(wrapper.find('[data-testid="cred-input-api_key"]').attributes('type')).toBe('password')
    expect(wrapper.find('[data-testid="cred-input-api_secret"]').attributes('type')).toBe('password')
  })

  it('renders select dropdown for select type fields', () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    const select = wrapper.find('[data-testid="cred-input-auth_mode"]')
    expect(select.element.tagName).toBe('SELECT')
    const options = select.findAll('option')
    expect(options).toHaveLength(2)
    expect(options[0].text()).toBe('Personal Access Token')
    expect(options[1].text()).toBe('GitHub App')
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

  it('shows App fields when auth_mode is switched to app', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    const select = wrapper.find('[data-testid="cred-input-auth_mode"]')
    await select.setValue('app')

    // App fields visible
    expect(wrapper.find('[data-testid="cred-input-app_id"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cred-input-private_key"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cred-input-installation_id"]').exists()).toBe(true)
    // PAT field hidden
    expect(wrapper.find('[data-testid="cred-input-personal_access_token"]').exists()).toBe(false)
  })

  it('renders textarea for textarea type fields', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    await wrapper.find('[data-testid="cred-input-auth_mode"]').setValue('app')

    const textarea = wrapper.find('[data-testid="cred-input-private_key"]')
    expect(textarea.element.tagName).toBe('TEXTAREA')
  })

  it('renders text inputs for text type fields', async () => {
    const wrapper = mount(PlatformCredentialForm, {
      props: { schema: githubSchema, saving: false },
    })

    await wrapper.find('[data-testid="cred-input-auth_mode"]').setValue('app')

    expect(wrapper.find('[data-testid="cred-input-app_id"]').attributes('type')).toBe('text')
    expect(wrapper.find('[data-testid="cred-input-installation_id"]').attributes('type')).toBe('text')
  })

  it('only submits visible fields', async () => {
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

    await wrapper.find('[data-testid="cred-input-auth_mode"]').setValue('app')
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
})
