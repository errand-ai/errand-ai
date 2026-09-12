/**
 * Integration guard for the provider settings card.
 *
 * Mounts the real `LlmProviderCard` from the installed `@errand-ai/ui-components`
 * — not a stub — and feeds it API responses captured verbatim from this repo's
 * own endpoints (`fixtures/provider-api-capture.json`, produced by driving the
 * FastAPI app with its test client).
 *
 * What this asserts is the seam between the two repositories, which neither
 * suite sees on its own: the library tests its rendering against fixtures it
 * wrote, and errand tests its responses against fixtures it wrote. Whether the
 * fields one emits are the fields the other reads is checked only here — and
 * there are eight response shapes to get wrong, not one — the scan result
 * grew a `needs_key` list, and adoption answers with four distinct refusals
 * plus a success.
 *
 * One mismatch is already known and pinned below: the server sends
 * `base_url: null` for the two catalog entries that require a caller-supplied
 * URL, while the library types it `string`. TypeScript cannot catch that across
 * a JSON boundary, so it is asserted at runtime instead.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { LlmProviderCard, createErrandUI, type ServerCapabilities } from '@errand-ai/ui-components'

import capture from './fixtures/provider-api-capture.json'

const flush = async () => {
  await nextTick()
  await new Promise((r) => setTimeout(r, 0))
  await nextTick()
}

function makeApi(overrides: Record<string, unknown> = {}) {
  return {
    getProviders: vi.fn().mockResolvedValue(capture.providers),
    getProviderCatalog: vi.fn().mockResolvedValue(capture.catalog),
    scanLocalAi: vi.fn().mockResolvedValue(capture.scan_found),
    checkProviderReachability: vi.fn().mockResolvedValue(capture.reachability_down),
    getProviderModels: vi.fn().mockResolvedValue(capture.models),
    createProvider: vi.fn().mockResolvedValue(capture.providers[0]),
    updateProvider: vi.fn().mockResolvedValue(capture.providers[0]),
    deleteProvider: vi.fn().mockResolvedValue(undefined),
    setDefaultProvider: vi.fn().mockResolvedValue(capture.providers[0]),
    adoptLocalAiProvider: vi.fn().mockResolvedValue(capture.adopt_success),
    ...overrides,
  }
}

async function mountCard(api: ReturnType<typeof makeApi>) {
  // The injection keys are internal to the library, so the API can only be
  // supplied the way a real consumer supplies it: through the plugin.
  const capabilities = ref<ServerCapabilities>({
    version: '0.150.0',
    capabilities: ['llm_providers'],
    connected: true,
  })
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- duplicate Vue type trees under npm workspaces
  const errandUI = createErrandUI({ api: api as any, capabilities })

  const wrapper = mount(LlmProviderCard, {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- as above
    global: { plugins: [{ install: (a: any) => errandUI.install(a) }] },
  })
  await flush()
  return wrapper
}

function rowFor(wrapper: ReturnType<typeof mount>, name: string) {
  return wrapper
    .findAll('[data-testid="llm-provider-row"]')
    .find((r) => r.text().includes(name))
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('provider list: the source field errand emits', () => {
  it('labels the detected provider the scan created', async () => {
    const wrapper = await mountCard(makeApi())

    const row = rowFor(wrapper, 'ollama')
    expect(row).toBeDefined()
    expect(row!.find('[data-testid="llm-provider-detected-badge"]').exists()).toBe(true)
  })

  it('does not label the hand-configured provider as detected', async () => {
    const wrapper = await mountCard(makeApi())

    const row = rowFor(wrapper, 'my-proxy')
    expect(row!.find('[data-testid="llm-provider-detected-badge"]').exists()).toBe(false)
    expect(row!.find('[data-testid="llm-provider-default-badge"]').exists()).toBe(true)
  })

  it('shows the gateway URL the scan stored, not localhost', async () => {
    const wrapper = await mountCard(makeApi())

    expect(rowFor(wrapper, 'ollama')!.text()).toContain('host.docker.internal:11434')
  })

  it('does not let a detected provider\'s address be hand-edited', async () => {
    const wrapper = await mountCard(makeApi())

    // Renaming one is fine; retyping its address is not, because the next scan
    // reconciles that field and would overwrite whatever was typed.
    await rowFor(wrapper, 'ollama')!.find('[data-testid="llm-provider-edit"]').trigger('click')
    await flush()
    expect(wrapper.find('[data-testid="llm-provider-edit-base-url"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="llm-provider-edit-name"]').exists()).toBe(true)
    // In edit mode the name moves into an input, so the row no longer matches by text.
    expect(wrapper.text()).toContain('refreshed by the next scan')
    expect(wrapper.text()).toContain('host.docker.internal:11434')
  })

  it('does let a hand-configured provider\'s address be edited', async () => {
    const wrapper = await mountCard(makeApi())

    await rowFor(wrapper, 'my-proxy')!.find('[data-testid="llm-provider-edit"]').trigger('click')
    await flush()
    expect(wrapper.find('[data-testid="llm-provider-edit-base-url"]').exists()).toBe(true)
  })

  it('withholds edit and delete from an env-sourced provider', async () => {
    const envProvider = { ...capture.providers[0], id: 'env-1', name: 'from-env', source: 'env', is_default: false }
    const wrapper = await mountCard(makeApi({
      getProviders: vi.fn().mockResolvedValue([...capture.providers, envProvider]),
    }))

    const row = rowFor(wrapper, 'from-env')!
    // The server answers 403 for both; offering them makes that an unexplained
    // save failure.
    expect(row.find('[data-testid="llm-provider-edit"]').exists()).toBe(false)
    expect(row.find('[data-testid="llm-provider-delete"]').exists()).toBe(false)
    expect(row.find('[data-testid="llm-provider-env-badge"]').exists()).toBe(true)
  })
})

describe('catalog: the shape errand serves', () => {
  it('is not fetched until the create form is opened', async () => {
    const api = makeApi()
    const wrapper = await mountCard(api)

    expect(api.getProviderCatalog).not.toHaveBeenCalled()

    await wrapper.find('[data-testid="llm-provider-add"]').trigger('click')
    await flush()

    expect(api.getProviderCatalog).toHaveBeenCalledTimes(1)
  })

  it('offers every entry errand serves, including the unlisted one', async () => {
    const wrapper = await mountCard(makeApi())
    await wrapper.find('[data-testid="llm-provider-add"]').trigger('click')
    await flush()

    const options = wrapper.find('[data-testid="llm-provider-catalog-select"]').findAll('option')
    const values = options.map((o) => o.attributes('value')).filter(Boolean)
    expect(values).toContain('openrouter')
    expect(values).toContain('other')
    expect(values.length).toBeGreaterThanOrEqual(capture.catalog.length)
  })

  it('asks only for a key when a listed entry is chosen, and links to where to get one', async () => {
    const wrapper = await mountCard(makeApi())
    await wrapper.find('[data-testid="llm-provider-add"]').trigger('click')
    await flush()

    await wrapper.find('[data-testid="llm-provider-catalog-select"]').setValue('openrouter')
    await flush()

    expect(wrapper.find('[data-testid="llm-provider-new-base-url"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="llm-provider-new-api-key"]').exists()).toBe(true)

    const link = wrapper.find('[data-testid="llm-provider-key-link"]')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://openrouter.ai/keys')
  })

  it('reveals a base URL field for an entry errand marks requires_base_url', async () => {
    const wrapper = await mountCard(makeApi())
    await wrapper.find('[data-testid="llm-provider-add"]').trigger('click')
    await flush()

    await wrapper.find('[data-testid="llm-provider-catalog-select"]').setValue('other')
    await flush()

    expect(wrapper.find('[data-testid="llm-provider-new-base-url"]').exists()).toBe(true)
  })

  it('survives the null base_url errand sends for those entries', async () => {
    // The library types base_url as `string`; errand sends null wherever
    // requires_base_url is true. TypeScript cannot see across the JSON
    // boundary, so the guard is here.
    expect(capture.catalog.filter((e) => e.requires_base_url).map((e) => e.base_url))
      .toEqual([null, null])

    const wrapper = await mountCard(makeApi())
    await wrapper.find('[data-testid="llm-provider-add"]').trigger('click')
    await flush()
    await wrapper.find('[data-testid="llm-provider-catalog-select"]').setValue('litellm')
    await flush()

    expect(wrapper.text()).not.toContain('null')
  })

  it('sends the catalog selection, not a base URL it invented', async () => {
    const api = makeApi()
    const wrapper = await mountCard(api)
    await wrapper.find('[data-testid="llm-provider-add"]').trigger('click')
    await flush()

    await wrapper.find('[data-testid="llm-provider-catalog-select"]').setValue('openrouter')
    await flush()
    await wrapper.find('[data-testid="llm-provider-new-api-key"]').setValue('sk-or-test')
    await wrapper.find('[data-testid="llm-provider-create-submit"]').trigger('click')
    await flush()

    expect(api.createProvider).toHaveBeenCalledTimes(1)
    const sent = api.createProvider.mock.calls[0][0]
    expect(sent.catalog_id).toBe('openrouter')
    expect(sent.api_key).toBe('sk-or-test')
    expect(sent.base_url).toBeFalsy()
  })

  it('falls back to typed entry when the catalog cannot be served', async () => {
    // An errand older than this change has no catalog endpoint.
    const api = makeApi({
      getProviderCatalog: vi.fn().mockRejectedValue(new Error('404 Not Found')),
    })
    const wrapper = await mountCard(api)
    await wrapper.find('[data-testid="llm-provider-add"]').trigger('click')
    await flush()

    expect(wrapper.find('[data-testid="llm-provider-new-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="llm-provider-new-base-url"]').exists()).toBe(true)
  })
})

describe('scan: available vs found', () => {
  it('does not scan on mount', async () => {
    const api = makeApi()
    await mountCard(api)

    // A scan reconciles provider rows, deleting those that no longer answer.
    expect(api.scanLocalAi).not.toHaveBeenCalled()
  })

  it('presents what errand detected', async () => {
    const api = makeApi()
    const wrapper = await mountCard(api)

    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    expect(api.scanLocalAi).toHaveBeenCalledTimes(1)
    const results = wrapper.find('[data-testid="llm-provider-scan-results"]')
    expect(results.text()).toContain('ollama')
    expect(results.text()).toContain('host.docker.internal:11434')
  })

  it('reports an empty scan without calling it an error', async () => {
    const wrapper = await mountCard(makeApi({
      scanLocalAi: vi.fn().mockResolvedValue({ available: true, detected: [], needs_key: [], message: null }),
    }))

    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    const message = wrapper.find('[data-testid="llm-provider-scan-message"]').text().toLowerCase()
    expect(message).toContain('no local ai')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('says detection is unavailable rather than that nothing was found', async () => {
    // On Kubernetes there is no host to probe. Telling the user to go start
    // Ollama would send them somewhere that can never work.
    const wrapper = await mountCard(makeApi({
      scanLocalAi: vi.fn().mockResolvedValue(capture.scan_unavailable),
    }))

    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    const message = wrapper.find('[data-testid="llm-provider-scan-message"]').text().toLowerCase()
    expect(message).toContain('not available')
    expect(message).not.toContain('no local ai was found')
  })
})

describe('keyed runtimes: the needs_key list errand emits', () => {
  it('offers a runtime that answered but demanded a key', async () => {
    // Before this shape existed the scan reported such a runtime as absent.
    // Presenting it as found-but-locked is the entire point.
    const wrapper = await mountCard(makeApi())

    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    const entries = wrapper.findAll('[data-testid="llm-provider-needs-key-entry"]')
    expect(entries.length).toBe(capture.scan_found.needs_key.length)
    expect(entries[0].text()).toContain('host.docker.internal:1234')
    expect(entries[0].find('[data-testid="llm-provider-adopt-key"]').exists()).toBe(true)
  })

  it('shows a registered runtime and a keyed one at the same time, distinguished', async () => {
    // The realistic shape, and the machine this was captured from: Ollama
    // answering unauthenticated while LM Studio and oMLX demand a key.
    const wrapper = await mountCard(makeApi())

    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    expect(wrapper.find('[data-testid="llm-provider-scan-results"]').text()).toContain('ollama')
    expect(wrapper.find('[data-testid="llm-provider-needs-key-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="llm-provider-needs-key-list"]').text())
      .not.toContain('ollama')
  })

  it('does not present a keyed runtime as an error', async () => {
    // It is a success: the scan found a working OpenAI-compatible server.
    const wrapper = await mountCard(makeApi())

    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="llm-provider-scan-message"]').text().toLowerCase())
      .not.toContain('no local ai')
  })

  it('sends the base_url errand gave it, unaltered', async () => {
    // errand matches detected providers on this string. A URL the card
    // reconstructs rather than echoes is one a later scan may not match.
    const api = makeApi()
    const wrapper = await mountCard(api)
    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    const entry = wrapper.findAll('[data-testid="llm-provider-needs-key-entry"]')[0]
    await entry.find('[data-testid="llm-provider-adopt-key"]').setValue('sk-supplied')
    await entry.find('[data-testid="llm-provider-adopt"]').trigger('click')
    await flush()

    expect(api.adoptLocalAiProvider).toHaveBeenCalledTimes(1)
    const sent = api.adoptLocalAiProvider.mock.calls[0][0]
    expect(sent.base_url).toBe(capture.scan_found.needs_key[0].base_url)
    expect(sent.api_key).toBe('sk-supplied')
  })

  it('hides the supplied key from the page', async () => {
    const wrapper = await mountCard(makeApi())
    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()

    const field = wrapper.findAll('[data-testid="llm-provider-needs-key-entry"]')[0]
      .find('[data-testid="llm-provider-adopt-key"]')
    expect(field.attributes('type')).toBe('password')
  })
})

describe('adoption: the four refusals errand distinguishes', () => {
  async function adoptWith(response: unknown) {
    const api = makeApi({ adoptLocalAiProvider: vi.fn().mockResolvedValue(response) })
    const wrapper = await mountCard(api)
    await wrapper.find('[data-testid="llm-provider-scan"]').trigger('click')
    await flush()
    const entry = wrapper.findAll('[data-testid="llm-provider-needs-key-entry"]')[0]
    await entry.find('[data-testid="llm-provider-adopt-key"]').setValue('sk-try')
    await entry.find('[data-testid="llm-provider-adopt"]').trigger('click')
    await flush()
    return { wrapper, api }
  }

  it('takes the created provider on success, api_key already masked', async () => {
    // The provider dict is where the library's type was wrong for eight
    // releases: it declared has_api_key, which errand has never sent.
    expect(capture.adopt_success.provider).toHaveProperty('api_key')
    expect(capture.adopt_success.provider).not.toHaveProperty('has_api_key')
    expect(capture.adopt_success.provider.api_key).toMatch(/\*\*\*\*$/)

    const { wrapper, api } = await adoptWith(capture.adopt_success)

    expect(api.getProviders.mock.calls.length).toBeGreaterThan(1)
    expect(wrapper.text()).not.toContain('sk-try')
  })

  it('explains a rejected key and keeps the runtime available to retry', async () => {
    const { wrapper } = await adoptWith(capture.adopt_key_rejected)

    expect(wrapper.find('[data-testid="llm-provider-adopt-message"]').text().toLowerCase())
      .toContain('key')
    expect(wrapper.findAll('[data-testid="llm-provider-needs-key-entry"]').length)
      .toBe(capture.scan_found.needs_key.length)
  })

  it('distinguishes an endpoint that stopped answering from a bad key', async () => {
    // A runtime can go away between the scan and the adopt. Saying the key was
    // rejected there would be false.
    const { wrapper } = await adoptWith(capture.adopt_unreachable)

    const msg = wrapper.find('[data-testid="llm-provider-adopt-message"]').text().toLowerCase()
    expect(msg).not.toContain('did not accept')
  })

  it('names the conflicting provider and offers a name to resolve it', async () => {
    expect(capture.adopt_name_conflict.conflicting_name).toBeTruthy()

    const { wrapper } = await adoptWith(capture.adopt_name_conflict)

    expect(wrapper.find('[data-testid="llm-provider-adopt-message"]').text())
      .toContain(capture.adopt_name_conflict.conflicting_name)
    expect(wrapper.find('[data-testid="llm-provider-adopt-name"]').exists()).toBe(true)
  })

  it('does not offer a name for an endpoint that is already configured', async () => {
    // The fourth reason, added after the card shipped against three. A caller
    // whose final branch was name_conflict would advise a new name here — for a
    // refusal that has nothing to do with the name.
    expect(capture.adopt_already_configured.reason).toBe('already_configured')

    const { wrapper } = await adoptWith(capture.adopt_already_configured)

    expect(wrapper.find('[data-testid="llm-provider-adopt-message"]').text())
      .toContain(capture.adopt_already_configured.conflicting_name)
    expect(wrapper.find('[data-testid="llm-provider-adopt-name"]').exists()).toBe(false)
  })

  it('falls back to errand\'s message for a reason it does not know', async () => {
    // `reason` is an open set. A consumer that maps an unknown value onto its
    // nearest known branch misadvises the user; the contract says render
    // `message`, which is why message is required on every refusal.
    const { wrapper } = await adoptWith({
      adopted: false,
      reason: 'some_future_reason',
      message: 'A reason this card has never heard of.',
    })

    expect(wrapper.find('[data-testid="llm-provider-adopt-message"]').text())
      .toContain('A reason this card has never heard of.')
  })
})

describe('reachability', () => {
  it('renders the list before reachability resolves, claiming nothing meanwhile', async () => {
    let release: (v: unknown) => void = () => {}
    const api = makeApi({
      checkProviderReachability: vi.fn().mockReturnValue(new Promise((r) => { release = r })),
    })
    const wrapper = await mountCard(api)

    expect(wrapper.findAll('[data-testid="llm-provider-row"]').length).toBe(capture.providers.length)
    const states = wrapper.findAll('[data-testid="llm-provider-reachability"]').map((n) => n.text())
    expect(states.every((s) => /unknown|checking/i.test(s))).toBe(true)

    release(capture.reachability_up)
    await flush()
  })

  it('marks a provider errand reports as down', async () => {
    const wrapper = await mountCard(makeApi())

    const row = rowFor(wrapper, 'my-proxy')!
    expect(row.find('[data-testid="llm-provider-reachability"]').text().toLowerCase())
      .toContain('unreachable')
  })

  it('re-checks on request without touching stored configuration', async () => {
    const api = makeApi()
    const wrapper = await mountCard(api)
    const before = api.checkProviderReachability.mock.calls.length

    await rowFor(wrapper, 'my-proxy')!.find('[data-testid="llm-provider-recheck"]').trigger('click')
    await flush()

    expect(api.checkProviderReachability.mock.calls.length).toBeGreaterThan(before)
    expect(api.updateProvider).not.toHaveBeenCalled()
  })
})

describe('models: the mode field errand resolves', () => {
  it('lists what errand returned, including a model of unknown mode', async () => {
    const wrapper = await mountCard(makeApi())
    await rowFor(wrapper, 'ollama')!.find('[data-testid="llm-provider-models-toggle"]').trigger('click')
    await flush()

    const listed = wrapper.findAll('[data-testid="llm-provider-model-option"]').map((n) => n.text())
    expect(listed.join(' ')).toContain('qwen3:8b')
    // mode: null must not be dropped — a model the registry does not know is
    // still a model the user may want.
    expect(listed.join(' ')).toContain('mystery-7b')
  })

  it('filters by typing rather than requiring a scroll', async () => {
    const many = Array.from({ length: 300 }, (_, i) => ({
      id: `vendor/model-${i}`, supports_reasoning: null, max_output_tokens: null, mode: 'chat',
    }))
    const wrapper = await mountCard(makeApi({
      getProviderModels: vi.fn().mockResolvedValue(many),
    }))
    await rowFor(wrapper, 'ollama')!.find('[data-testid="llm-provider-models-toggle"]').trigger('click')
    await flush()

    await wrapper.find('[data-testid="llm-provider-model-input"]').setValue('model-42')
    await flush()

    const shown = wrapper.findAll('[data-testid="llm-provider-model-option"]')
    expect(shown.length).toBeLessThan(many.length)
    expect(shown.some((n) => n.text().includes('model-42'))).toBe(true)
  })

  it('offers typed entry and says why when listing fails', async () => {
    const wrapper = await mountCard(makeApi({
      getProviderModels: vi.fn().mockRejectedValue(new Error('502 Bad Gateway')),
    }))
    await rowFor(wrapper, 'ollama')!.find('[data-testid="llm-provider-models-toggle"]').trigger('click')
    await flush()

    expect(wrapper.find('[data-testid="llm-provider-model-input"]').exists()).toBe(true)
    // Silence here would be indistinguishable from a list still loading.
    expect(wrapper.find('[data-testid="llm-provider-model-note"]').text()).toBeTruthy()
  })
})
