/**
 * Integration test for capability gating of shared settings cards.
 *
 * Unlike the other SettingsPage tests, this one uses the REAL
 * `@errand-ai/ui-components` library (plugin + cards). The library's
 * `<CapabilityGate>` reads the capabilities Ref provided to `createErrandUI`
 * via an internal injection key, so gating can only be exercised by driving
 * that ref — mocking the exported `useCapabilities` would not affect it.
 *
 * Post-Wave-2 IntegrationsPage composes four library cards; this covers the
 * gating for the two conditional ones (google_workspace, cloud_storage) plus
 * the always-on platforms card.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createErrandUI, createDirectApi, type ServerCapabilities } from '@errand-ai/ui-components'
import IntegrationsPage from '../settings/IntegrationsPage.vue'

vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

function mountWithCapabilities(capabilities: string[]) {
  const capsRef = ref<ServerCapabilities>({
    version: 'test',
    capabilities,
    connected: true,
  })
  const api = createDirectApi({
    baseUrl: '/api',
    getToken: () => null,
    onUnauthorized: () => {},
    onForbidden: () => {},
    refreshToken: async () => false,
  })
  const errandUI = createErrandUI({ api, capabilities: capsRef })
  return mount(IntegrationsPage, {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- duplicate Vue type trees under npm workspaces
    global: { plugins: [{ install: (a: any) => errandUI.install(a) }] },
  })
}

describe('Integrations capability gating', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // Note: the library's capability check is permissive when the capabilities
  // list is empty (treats it as "info unavailable" and shows the card). A server
  // that omits a conditional key still advertises the always-on keys, so the
  // "absent" case is a non-empty list that lacks the key under test.
  it('hides CloudStorageCard when the cloud_storage capability is absent', async () => {
    const wrapper = mountWithCapabilities(['system_prompt', 'mcp_servers', 'telemetry'])
    await flushPromises()

    expect(wrapper.text()).not.toContain('Cloud storage')
  })

  it('shows CloudStorageCard when the cloud_storage capability is present', async () => {
    const wrapper = mountWithCapabilities(['system_prompt', 'cloud_storage'])
    await flushPromises()

    expect(wrapper.text()).toContain('Cloud storage')
  })

  it('hides GoogleWorkspaceCard when the google_workspace capability is absent', async () => {
    const wrapper = mountWithCapabilities(['system_prompt', 'platforms'])
    await flushPromises()

    expect(wrapper.text()).not.toContain('Google Workspace')
  })

  it('shows GoogleWorkspaceCard when the google_workspace capability is present', async () => {
    const wrapper = mountWithCapabilities(['system_prompt', 'google_workspace'])
    await flushPromises()

    expect(wrapper.text()).toContain('Google Workspace')
  })

  it('shows PlatformsCard when the platforms capability is present', async () => {
    const wrapper = mountWithCapabilities(['system_prompt', 'platforms'])
    await flushPromises()

    expect(wrapper.text()).toContain('Platform credentials')
  })
})
