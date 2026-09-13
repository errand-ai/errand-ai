import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent } from 'vue'
import { useAuthStore } from '../../stores/auth'
import SetupWizard from '../SetupWizard.vue'

// Mock vue-sonner
const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake`
}

const FAKE_PROVIDER_ID = '11111111-1111-1111-1111-111111111111'

const DummyPage = defineComponent({ template: '<div>dummy</div>' })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: DummyPage },
      { path: '/setup', name: 'setup', component: SetupWizard },
      { path: '/settings', name: 'settings', component: DummyPage },
    ],
  })
}

describe('SetupWizard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.setAuthMode('setup')
    toastMock.success.mockClear()
    toastMock.error.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  async function mountSetup() {
    const router = makeRouter()
    await router.push('/setup')
    await router.isReady()
    const wrapper = mount(SetupWizard, { global: { plugins: [router] } })
    await flushPromises()
    return { wrapper, router }
  }

  /** Helper: stub fetch for step 1 → step 2 transition (no existing providers) */
  function stubStep1ToStep2() {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      // GET /api/llm/providers — no providers yet
      if (url === '/api/llm/providers') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))
    return token
  }

  /** Helper: advance wrapper through step 1 to step 2 */
  async function completeStep1(wrapper: ReturnType<typeof mount>) {
    await wrapper.find('[data-testid="setup-username"]').setValue('admin')
    await wrapper.find('[data-testid="setup-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-step1"]').find('form').trigger('submit')
    await flushPromises()
  }

  it('renders step 1 initially', async () => {
    const { wrapper } = await mountSetup()

    expect(wrapper.find('[data-testid="setup-step1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Create Admin Account')
    expect(wrapper.find('[data-testid="setup-username"]').exists()).toBe(true)
  })

  it('shows step indicators', async () => {
    const { wrapper } = await mountSetup()

    const steps = wrapper.find('[data-testid="setup-steps"]')
    expect(steps.exists()).toBe(true)
  })

  it('shows password mismatch error', async () => {
    const { wrapper } = await mountSetup()

    await wrapper.find('[data-testid="setup-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('different')

    expect(wrapper.find('[data-testid="setup-password-mismatch"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-password-mismatch"]').text()).toBe('Passwords do not match.')
  })

  it('shows error for short password', async () => {
    vi.stubGlobal('fetch', vi.fn())

    const { wrapper } = await mountSetup()

    await wrapper.find('[data-testid="setup-username"]').setValue('admin')
    await wrapper.find('[data-testid="setup-password"]').setValue('short')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('short')
    await wrapper.find('[data-testid="setup-step1"]').find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step1-error"]').text()).toBe('Password must be at least 8 characters.')
  })

  it('advances to step 2 after creating admin', async () => {
    stubStep1ToStep2()

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    expect(wrapper.find('[data-testid="setup-step2"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('LLM Provider Configuration')
  })

  it('shows step 2 with provider name, test connection and continue buttons', async () => {
    stubStep1ToStep2()

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    expect(wrapper.find('[data-testid="setup-provider-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-test-connection"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-continue-step2"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-provider-url"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-api-key"]').exists()).toBe(true)
  })

  it('shows inline success message after successful test connection', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      // GET /api/llm/providers — no providers yet
      if (url === '/api/llm/providers' && (!opts || opts.method === undefined || opts.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        })
      }
      // POST /api/llm/providers — create provider
      if (url === '/api/llm/providers' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: FAKE_PROVIDER_ID, name: 'default', base_url: 'https://api.example.com/v1', source: 'database' }),
        })
      }
      // GET /api/llm/providers/{id}/models
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(['model-a', 'model-b']),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    // Fill in LLM provider fields
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://api.example.com/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-test-key')

    // Click Test Connection
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()

    // Verify inline success message
    expect(wrapper.find('[data-testid="setup-step2-success"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-step2-success"]').text()).toBe('Connection successful')

    // Verify button text changed
    expect(wrapper.find('[data-testid="setup-test-connection"]').text()).toContain('Connection Verified')
  })

  it('clears success state when provider URL changes', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      if (url === '/api/llm/providers' && (!opts || opts.method === undefined || opts.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        })
      }
      if (url === '/api/llm/providers' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: FAKE_PROVIDER_ID, name: 'default', base_url: 'https://api.example.com/v1', source: 'database' }),
        })
      }
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(['model-a', 'model-b']),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    // Fill in LLM provider fields and test connection
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://api.example.com/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-test-key')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()

    // Verify success state exists
    expect(wrapper.find('[data-testid="setup-step2-success"]').exists()).toBe(true)

    // Change provider URL
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://other.example.com/v1')
    await flushPromises()

    // Verify success state cleared
    expect(wrapper.find('[data-testid="setup-step2-success"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="setup-test-connection"]').text()).not.toContain('Connection Verified')
  })

  it('handles create-user API error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'User already exists' }),
    }))

    const { wrapper } = await mountSetup()

    await wrapper.find('[data-testid="setup-username"]').setValue('admin')
    await wrapper.find('[data-testid="setup-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-confirm-password"]').setValue('password123')
    await wrapper.find('[data-testid="setup-step1"]').find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step1-error"]').text()).toBe('User already exists')
  })

  it('pre-fills fields as readonly when env-sourced provider exists', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    const envProvider = {
      id: FAKE_PROVIDER_ID,
      name: 'litellm',
      base_url: 'https://litellm.example.com/v1',
      api_key: 'sk-t****',
      provider_type: 'litellm',
      is_default: true,
      source: 'env',
    }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      if (url === '/api/llm/providers') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([envProvider]),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    }))

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    // Fields should be pre-filled
    const nameInput = wrapper.find('[data-testid="setup-provider-name"]').element as HTMLInputElement
    const urlInput = wrapper.find('[data-testid="setup-provider-url"]').element as HTMLInputElement
    const keyInput = wrapper.find('[data-testid="setup-api-key"]').element as HTMLInputElement
    expect(nameInput.value).toBe('litellm')
    expect(urlInput.value).toBe('https://litellm.example.com/v1')
    expect(keyInput.value).toBe('sk-t****')

    // All fields should be readonly (disabled) when a provider exists
    expect(nameInput.disabled).toBe(true)
    expect(urlInput.disabled).toBe(true)
    expect(keyInput.disabled).toBe(true)
  })

  it('does not create a new provider when testing connection with env-sourced provider', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    const envProvider = {
      id: FAKE_PROVIDER_ID,
      name: 'litellm',
      base_url: 'https://litellm.example.com/v1',
      api_key: 'sk-t****',
      provider_type: 'litellm',
      is_default: true,
      source: 'env',
    }
    const fetchMock = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      if (url === '/api/llm/providers' && (!opts || opts.method === undefined || opts.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([envProvider]),
        })
      }
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(['model-a']),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    // Click test connection
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()

    // Verify no POST to /api/llm/providers was made
    const postCalls = fetchMock.mock.calls.filter(
      (call: unknown[]) => call[0] === '/api/llm/providers' && (call[1] as RequestInit | undefined)?.method === 'POST'
    )
    expect(postCalls).toHaveLength(0)

    // Verify models were fetched from the env provider
    const modelCalls = fetchMock.mock.calls.filter(
      (call: unknown[]) => call[0] === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`
    )
    expect(modelCalls).toHaveLength(1)

    // Verify success
    expect(wrapper.find('[data-testid="setup-step2-success"]').exists()).toBe(true)
  })

  it('cleans up created provider when model fetch fails', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    const fetchMock = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      if (url === '/api/llm/providers' && (!opts || opts.method === undefined || opts.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        })
      }
      if (url === '/api/llm/providers' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: FAKE_PROVIDER_ID, name: 'default', base_url: 'https://bad.example.com', source: 'database' }),
        })
      }
      // Model fetch fails
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ detail: 'Connection failed' }),
        })
      }
      // DELETE cleanup
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}` && opts?.method === 'DELETE') {
        return Promise.resolve({ ok: true })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://bad.example.com')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-bad')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()

    // Verify DELETE was called to clean up the provider
    const deleteCalls = fetchMock.mock.calls.filter(
      (call: unknown[]) => call[0] === `/api/llm/providers/${FAKE_PROVIDER_ID}` && (call[1] as RequestInit | undefined)?.method === 'DELETE'
    )
    expect(deleteCalls).toHaveLength(1)

    // Verify error shown
    expect(wrapper.find('[data-testid="setup-step2-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="setup-step2-error"]').text()).toContain('Connection failed')

    // Verify connection is not marked as tested
    expect(wrapper.find('[data-testid="setup-step2-success"]').exists()).toBe(false)
  })

  it('saves model settings as {provider_id, model} objects on complete setup', async () => {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    const fetchMock = vi.fn().mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: token }),
        })
      }
      if (url === '/api/llm/providers' && (!opts || opts.method === undefined || opts.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([]),
        })
      }
      if (url === '/api/llm/providers' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: FAKE_PROVIDER_ID, name: 'default', base_url: 'https://api.example.com/v1', source: 'database' }),
        })
      }
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(['claude-haiku-4-5-20251001', 'claude-sonnet-4-5-20250929', 'model-c']),
        })
      }
      if (url === '/api/settings' && opts?.method === 'PUT') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    // Fill in provider and test connection
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://api.example.com/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-test')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()

    // Advance to step 3
    await wrapper.find('[data-testid="setup-continue-step2"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step3"]').exists()).toBe(true)

    // Choose models from what the provider actually serves. This previously
    // relied on pre-filled Claude ids being selected by default, which is the
    // behaviour the wizard no longer has.
    await wrapper.findAll('select')[0].setValue('claude-haiku-4-5-20251001')
    await wrapper.findAll('select')[1].setValue('claude-sonnet-4-5-20250929')
    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    // Find the PUT /api/settings call
    const settingsCalls = fetchMock.mock.calls.filter(
      (call: unknown[]) => call[0] === '/api/settings' && (call[1] as RequestInit | undefined)?.method === 'PUT'
    )
    expect(settingsCalls).toHaveLength(1)

    const body = JSON.parse((settingsCalls[0][1] as RequestInit).body as string)
    expect(body.llm_model).toEqual({ provider_id: FAKE_PROVIDER_ID, model: 'claude-haiku-4-5-20251001' })
    expect(body.task_processing_model).toEqual({ provider_id: FAKE_PROVIDER_ID, model: 'claude-sonnet-4-5-20250929' })
  })

  it('does not write a model the provider does not serve', async () => {
    // The defect: the wizard pre-filled Claude model ids, and a provider whose
    // listing did not contain them kept them selected anyway — so a user
    // setting up against Ollama had a Claude model written against their
    // provider. Every task then failed while the settings reported a model was
    // configured, which is worse than none: the server would report
    // `model_configured: true` and nothing would ask again.
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      if (url === '/api/llm/providers' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: FAKE_PROVIDER_ID, name: 'ollama', base_url: 'http://host.docker.internal:11434/v1', source: 'database' }),
        })
      }
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(['qwen3:8b', 'gemma-4-26b']) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('http://host.docker.internal:11434/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-no-key-required')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="setup-continue-step2"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    const settingsCalls = fetchMock.mock.calls.filter(
      (call: unknown[]) => call[0] === '/api/settings' && (call[1] as RequestInit | undefined)?.method === 'PUT'
    )
    for (const call of settingsCalls) {
      const body = JSON.parse((call[1] as RequestInit).body as string)
      for (const key of ['llm_model', 'task_processing_model']) {
        const chosen = body[key]?.model
        expect(chosen === '' || chosen === undefined || ['qwen3:8b', 'gemma-4-26b'].includes(chosen)).toBe(true)
      }
    }
  })

  it('handles the enriched objects the models endpoint really returns', async () => {
    // `/models` returns {id, supports_reasoning, max_output_tokens, mode}, not
    // strings. Every fixture in this file returned strings, so the wizard met
    // the real shape only in production — where it rendered "[object Object]"
    // and wrote an object where a model id belonged.
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      if (url === '/api/llm/providers' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: FAKE_PROVIDER_ID, name: 'ollama', base_url: 'http://h:11434/v1', source: 'database' }),
        })
      }
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            { id: 'qwen3:8b', supports_reasoning: false, max_output_tokens: 4096, mode: null },
          ]),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('http://h:11434/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-x')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="setup-continue-step2"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step3"]').text()).not.toContain('[object Object]')

    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    const settingsCalls = fetchMock.mock.calls.filter(
      (call: unknown[]) => call[0] === '/api/settings' && (call[1] as RequestInit | undefined)?.method === 'PUT'
    )
    expect(settingsCalls.length).toBeGreaterThan(0)
    const body = JSON.parse((settingsCalls[0][1] as RequestInit).body as string)
    expect(body.llm_model.model).toBe('qwen3:8b')
    expect(body.task_processing_model.model).toBe('qwen3:8b')
  })

  it('selects a provider\'s only model, because there is nothing to choose', async () => {
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      if (url === '/api/llm/providers' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: FAKE_PROVIDER_ID, name: 'ollama', base_url: 'http://h:11434/v1', source: 'database' }),
        })
      }
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(['only-one-model']) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('http://h:11434/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-x')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="setup-continue-step2"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    const settingsCalls = fetchMock.mock.calls.filter(
      (call: unknown[]) => call[0] === '/api/settings' && (call[1] as RequestInit | undefined)?.method === 'PUT'
    )
    expect(settingsCalls.length).toBeGreaterThan(0)
    const body = JSON.parse((settingsCalls[0][1] as RequestInit).body as string)
    expect(body.llm_model.model).toBe('only-one-model')
    expect(body.task_processing_model.model).toBe('only-one-model')
  })
})
