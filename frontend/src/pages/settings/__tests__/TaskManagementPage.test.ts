/**
 * Task Management tab against the REAL published `@errand-ai/ui-components`
 * cards. The tab's fields live entirely in the library, so a regression there
 * (unlabelled timeouts, runtime settings with no UI) is invisible to errand's
 * other tests — this guards the seam with the settings shapes errand returns.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createErrandUI, createDirectApi, type ServerCapabilities } from '@errand-ai/ui-components'
import TaskManagementPage from '../TaskManagementPage.vue'

vi.mock('vue-sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

function entry(value: unknown, source = 'database', readonly = false) {
  return { value, source, sensitive: false, readonly }
}

function settingsResponse(overrides: Record<string, unknown> = {}) {
  return {
    task_processing_model: entry({ provider_id: 'p1', model: 'm1', model_id: 'm1' }),
    task_processing_timeout: entry(600),
    title_generation_timeout: entry(120),
    transcription_timeout: entry(30),
    compaction_timeout: entry(180),
    compaction_max_tokens: entry(4096),
    archive_after_days: entry(3, 'default'),
    max_concurrent_tasks: entry(3, 'default'),
    timezone: entry('Europe/London'),
    task_runner_log_level: entry('DEBUG'),
    max_turns: entry(75),
    reasoning_effort: entry('high'),
    ...overrides,
  }
}

function stubFetch(settings: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      const path = String(url).split('?')[0]
      const isList = path.endsWith('/providers') || path.endsWith('/models')
      const body = path.endsWith('/api/settings') ? settings : isList ? [] : {}
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
    }),
  )
}

function mountPage() {
  const capabilities = ref<ServerCapabilities>({
    version: 'test',
    capabilities: ['task_management', 'llm_providers', 'llm_models', 'telemetry'],
    connected: true,
  })
  const api = createDirectApi({
    baseUrl: '/api',
    getToken: () => null,
    onUnauthorized: () => {},
    onForbidden: () => {},
    refreshToken: async () => false,
  })
  const errandUI = createErrandUI({ api, capabilities })
  return mount(TaskManagementPage, {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- duplicate Vue type trees under npm workspaces
    global: { plugins: [{ install: (a: any) => errandUI.install(a) }] },
  })
}

describe('Task Management tab', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('with every setting editable', () => {
    beforeEach(() => stubFetch(settingsResponse()))

    it('labels each LLM timeout even when it holds a value', async () => {
      const wrapper = mountPage()
      await flushPromises()

      const timeout = wrapper.get('[data-testid="llm-model-task-timeout"]')
      expect((timeout.element as HTMLInputElement).value).toBe('600')
      expect(timeout.element.closest('label')?.textContent).toContain('Timeout (seconds)')
      for (const role of ['title', 'transcription', 'compaction']) {
        const input = wrapper.get(`[data-testid="llm-model-${role}-timeout"]`)
        expect(input.element.closest('label')?.textContent).toContain('Timeout (seconds)')
      }
      const maxTokens = wrapper.get('[data-testid="llm-model-compaction-max-tokens"]')
      expect(maxTokens.element.closest('label')?.textContent).toContain('Max output tokens')
    })

    it('renders the restored and new task settings with their values', async () => {
      const wrapper = mountPage()
      await flushPromises()

      const value = (id: string) => (wrapper.get(`[data-testid="${id}"]`).element as HTMLInputElement).value
      expect(value('task-timezone')).toBe('Europe/London')
      expect(value('task-log-level')).toBe('DEBUG')
      expect(value('task-max-turns')).toBe('75')
      expect(value('task-reasoning-effort')).toBe('high')
      for (const id of ['task-timezone', 'task-log-level', 'task-max-turns', 'task-reasoning-effort']) {
        expect(wrapper.get(`[data-testid="${id}"]`).attributes('disabled')).toBeUndefined()
      }
    })
  })

  it('locks max turns when the server reports it as environment-sourced', async () => {
    stubFetch(settingsResponse({ max_turns: entry(300, 'env', true) }))
    const wrapper = mountPage()
    await flushPromises()

    const input = wrapper.get('[data-testid="task-max-turns"]')
    expect((input.element as HTMLInputElement).value).toBe('300')
    expect(input.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="task-max-turns-readonly-note"]').exists()).toBe(true)
  })

  it('hides the new fields on a server that does not return their keys', async () => {
    const legacy = settingsResponse()
    for (const key of ['timezone', 'task_runner_log_level', 'max_turns', 'reasoning_effort']) {
      delete (legacy as Record<string, unknown>)[key]
    }
    stubFetch(legacy)
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[data-testid="task-max-turns"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="task-archive-after-days"]').exists()).toBe(true)
  })
})
