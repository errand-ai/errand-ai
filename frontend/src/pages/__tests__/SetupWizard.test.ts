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

  /**
   * The wizard states which model errand should use; the server decides which
   * settings implement that. These tests are written against that operation,
   * not against `/api/settings` — the previous set asserted the wizard wrote
   * `llm_model` and `task_processing_model` itself, which is the shape this
   * change exists to remove: it names the roles in the caller, and it skips
   * the check that the provider actually serves the chosen model.
   */
  function stubWizard(opts: {
    models?: unknown[]
    selection?: { ok: boolean; status?: number; detail?: string }
  } = {}) {
    const token = fakeJwt({ sub: 'admin', _roles: ['admin'] })
    const models = opts.models ?? ['model-a', 'model-b', 'model-c']
    const selection = opts.selection ?? { ok: true }
    const fetchMock = vi.fn().mockImplementation((url: string, o?: RequestInit) => {
      if (url === '/api/setup/create-user') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ access_token: token }) })
      }
      if (url === '/api/llm/providers' && (!o || o.method === undefined || o.method === 'GET')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
      }
      if (url === '/api/llm/providers' && o?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            id: FAKE_PROVIDER_ID,
            name: 'default',
            base_url: 'https://api.example.com/v1',
            source: 'database',
          }),
        })
      }
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(models) })
      }
      if (url === '/api/llm/model-selection' && o?.method === 'POST') {
        return Promise.resolve({
          ok: selection.ok,
          status: selection.status ?? (selection.ok ? 200 : 422),
          json: () => Promise.resolve(
            selection.ok
              ? { model_configured: true, provider_id: FAKE_PROVIDER_ID, model: 'model-a' }
              : { detail: selection.detail ?? 'refused' }
          ),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  async function reachStep3(wrapper: ReturnType<typeof mount>) {
    await completeStep1(wrapper)
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://api.example.com/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-test')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="setup-continue-step2"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="setup-step3"]').exists()).toBe(true)
  }

  function selectionCalls(fetchMock: ReturnType<typeof vi.fn>) {
    return fetchMock.mock.calls.filter(
      (call: unknown[]) =>
        call[0] === '/api/llm/model-selection' &&
        (call[1] as RequestInit | undefined)?.method === 'POST'
    )
  }

  function settingsWrites(fetchMock: ReturnType<typeof vi.fn>) {
    return fetchMock.mock.calls.filter(
      (call: unknown[]) =>
        call[0] === '/api/settings' && (call[1] as RequestInit | undefined)?.method === 'PUT'
    )
  }

  it('states the chosen model through the model-selection operation', async () => {
    const fetchMock = stubWizard()
    const { wrapper } = await mountSetup()
    await reachStep3(wrapper)

    await wrapper.find('[data-testid="setup-model"]').setValue('model-b')
    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    const calls = selectionCalls(fetchMock)
    expect(calls).toHaveLength(1)
    expect(JSON.parse((calls[0][1] as RequestInit).body as string)).toEqual({
      provider_id: FAKE_PROVIDER_ID,
      model: 'model-b',
    })
    // The role keys are the server's business. A wizard that writes them is a
    // caller carrying the current set of roles, so one added later leaves it
    // configuring a subset with the rest silently unset.
    expect(settingsWrites(fetchMock)).toHaveLength(0)
  })

  it('asks one question and says it governs both roles', async () => {
    // A question that decides more than it appears to is the same fault as
    // choosing a model on the user's behalf, arrived at from the other side.
    const fetchMock = stubWizard()
    const { wrapper } = await mountSetup()
    await reachStep3(wrapper)

    expect(wrapper.findAll('select')).toHaveLength(1)
    const scope = wrapper.find('[data-testid="setup-model-scope"]').text()
    expect(scope).toMatch(/runs your tasks/i)
    expect(scope).toMatch(/classifies new ones/i)
    expect(fetchMock).toBeTruthy()
  })

  it('shows the server\'s reason when a choice is refused', async () => {
    // The refusal is specific — the provider is gone, or does not serve that
    // model. Reporting a generic failure would hide the one sentence that
    // tells the user what to do about it.
    const fetchMock = stubWizard({
      selection: { ok: false, status: 422, detail: "default does not serve a model called 'model-b'." },
    })
    const { wrapper } = await mountSetup()
    await reachStep3(wrapper)

    await wrapper.find('[data-testid="setup-model"]').setValue('model-b')
    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="setup-step3-error"]').text()).toContain(
      "does not serve a model called 'model-b'"
    )
    expect(selectionCalls(fetchMock)).toHaveLength(1)
  })

  it('sends nothing when the user chose no model', async () => {
    // Leaving it unset is coherent: the server reports no model configured and
    // the provider settings say so. Writing an empty model was not — it records
    // a setting that names nothing, which reads as configured to anyone
    // checking the key exists.
    const fetchMock = stubWizard()
    const { wrapper } = await mountSetup()
    await reachStep3(wrapper)

    await wrapper.find('[data-testid="setup-model"]').setValue('')
    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    expect(selectionCalls(fetchMock)).toHaveLength(0)
    expect(settingsWrites(fetchMock)).toHaveLength(0)
    expect(toastMock.success).toHaveBeenCalled()
  })

  it('drops a selection the newly chosen provider does not serve', async () => {
    // A selection only means anything against the provider it was made for.
    // The template used to keep an unlisted value selected, so switching
    // provider sent the first one's model to the second.
    const fetchMock = stubWizard({ models: ['only-one-model'] })
    const { wrapper } = await mountSetup()
    await completeStep1(wrapper)

    // Provider A serves exactly one model, so the wizard selects it.
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://a.example.com/v1')
    await wrapper.find('[data-testid="setup-api-key"]').setValue('sk-test')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()

    // Provider B serves something else entirely. The selection made against A
    // must not survive into the call made for B.
    const original = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((url: string, o?: RequestInit) => {
      if (url === `/api/llm/providers/${FAKE_PROVIDER_ID}/models`) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(['different-model']) })
      }
      return original(url, o)
    })
    await wrapper.find('[data-testid="setup-provider-url"]').setValue('https://b.example.com/v1')
    await wrapper.find('[data-testid="setup-test-connection"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-testid="setup-continue-step2"]').trigger('click')
    await flushPromises()
    expect((wrapper.find('[data-testid="setup-model"]').element as HTMLSelectElement).value)
      .toBe('different-model')

    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    for (const call of selectionCalls(fetchMock)) {
      expect(JSON.parse((call[1] as RequestInit).body as string).model).not.toBe('only-one-model')
    }
  })

  it('handles the enriched objects the models endpoint really returns', async () => {
    // `/models` returns {id, mode, ...} objects, not strings. The wizard's own
    // fixtures returned strings, so nothing here ever met the real shape and
    // the dropdown rendered "[object Object]".
    const fetchMock = stubWizard({
      models: [
        { id: 'qwen3:8b', mode: 'chat', supports_reasoning: false },
        { id: 'nomic-embed-text', mode: 'embedding' },
      ],
    })
    const { wrapper } = await mountSetup()
    await reachStep3(wrapper)

    const options = wrapper.find('[data-testid="setup-model"]').findAll('option').map((o) => o.text())
    expect(options).toContain('qwen3:8b')
    expect(options.join(' ')).not.toContain('[object Object]')

    await wrapper.find('[data-testid="setup-model"]').setValue('qwen3:8b')
    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    const calls = selectionCalls(fetchMock)
    expect(calls).toHaveLength(1)
    expect(JSON.parse((calls[0][1] as RequestInit).body as string).model).toBe('qwen3:8b')
  })

  it("selects a provider's only model, because there is nothing to choose", async () => {
    const fetchMock = stubWizard({ models: ['only-one-model'] })
    const { wrapper } = await mountSetup()
    await reachStep3(wrapper)

    await wrapper.find('[data-testid="setup-complete"]').trigger('click')
    await flushPromises()

    const calls = selectionCalls(fetchMock)
    expect(calls).toHaveLength(1)
    expect(JSON.parse((calls[0][1] as RequestInit).body as string).model).toBe('only-one-model')
  })
})
