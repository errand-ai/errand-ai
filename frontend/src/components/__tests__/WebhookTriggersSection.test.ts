import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import WebhookTriggersSection from '../settings/WebhookTriggersSection.vue'

const { toastMock } = vi.hoisted(() => {
  const toastMock = { success: vi.fn(), error: vi.fn() }
  return { toastMock }
})
vi.mock('vue-sonner', () => ({ toast: toastMock }))

const mockFetchTriggers = vi.fn().mockResolvedValue([])
const mockFetchProfiles = vi.fn().mockResolvedValue([
  { id: 'p1', name: 'Default Profile' },
])
const mockFetchJiraStatus = vi.fn().mockResolvedValue({ status: 'connected' })
const mockFetchGithubStatus = vi.fn().mockResolvedValue({ status: 'disconnected' })
const mockCreateTrigger = vi.fn().mockResolvedValue({ id: 't1', name: 'Test', source: 'jira' })
const mockUpdateTrigger = vi.fn().mockResolvedValue({})
const mockDeleteTrigger = vi.fn().mockResolvedValue(undefined)
const mockIntrospectProject = vi.fn()

vi.mock('../../composables/useApi', () => ({
  fetchWebhookTriggers: (...args: any[]) => mockFetchTriggers(...args),
  fetchTaskProfiles: (...args: any[]) => mockFetchProfiles(...args),
  fetchJiraCredentialStatus: (...args: any[]) => mockFetchJiraStatus(...args),
  fetchGithubCredentialStatus: (...args: any[]) => mockFetchGithubStatus(...args),
  createWebhookTrigger: (...args: any[]) => mockCreateTrigger(...args),
  updateWebhookTrigger: (...args: any[]) => mockUpdateTrigger(...args),
  deleteWebhookTrigger: (...args: any[]) => mockDeleteTrigger(...args),
  introspectGithubProject: (...args: any[]) => mockIntrospectProject(...args),
}))

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/settings/integrations', component: { template: '<div />' } },
    ],
  })
}

async function mountComponent() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createTestRouter()
  router.push('/')
  await router.isReady()

  const wrapper = mount(WebhookTriggersSection, {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return wrapper
}

describe('WebhookTriggersSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetchTriggers.mockResolvedValue([])
    mockFetchJiraStatus.mockResolvedValue({ status: 'connected' })
    mockFetchGithubStatus.mockResolvedValue({ status: 'disconnected' })
  })

  it('renders empty state when no triggers', async () => {
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="no-triggers"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="add-trigger-btn"]').exists()).toBe(true)
  })

  it('shows credential warning when neither connected', async () => {
    mockFetchJiraStatus.mockResolvedValue({ status: 'disconnected' })
    mockFetchGithubStatus.mockResolvedValue({ status: 'disconnected' })
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="no-credentials"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="add-trigger-btn"]').attributes('disabled')).toBeDefined()
  })

  it('enables add button when only github is connected', async () => {
    mockFetchJiraStatus.mockResolvedValue({ status: 'disconnected' })
    mockFetchGithubStatus.mockResolvedValue({ status: 'connected' })
    const wrapper = await mountComponent()
    expect(wrapper.find('[data-testid="no-credentials"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="add-trigger-btn"]').attributes('disabled')).toBeUndefined()
  })

  it('renders trigger list', async () => {
    mockFetchTriggers.mockResolvedValue([
      { id: 't1', name: 'Jira Bugs', source: 'jira', enabled: true, has_secret: true, filters: {}, actions: {}, profile_id: null, task_prompt: null },
      { id: 't2', name: 'Jira Tasks', source: 'jira', enabled: false, has_secret: false, filters: {}, actions: {}, profile_id: null, task_prompt: null },
    ])
    const wrapper = await mountComponent()
    const rows = wrapper.findAll('[data-testid="trigger-row"]')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('Jira Bugs')
    expect(rows[1].text()).toContain('Jira Tasks')
  })

  it('opens create form on button click', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
    expect(wrapper.find('[data-testid="trigger-form"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trigger-name"]').exists()).toBe(true)
  })

  it('validates name is required', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
    await wrapper.find('[data-testid="trigger-save-btn"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="name-error"]').exists()).toBe(true)
    expect(mockCreateTrigger).not.toHaveBeenCalled()
  })

  it('creates trigger on save', async () => {
    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')

    await wrapper.find('[data-testid="trigger-name"]').setValue('Jira Bugs')
    await wrapper.find('[data-testid="trigger-save-btn"]').trigger('click')
    await flushPromises()

    expect(mockCreateTrigger).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Jira Bugs', source: 'jira' }),
    )
    expect(toastMock.success).toHaveBeenCalledWith('Trigger created')
  })

  it('generates a webhook secret', async () => {
    // Mock crypto.getRandomValues
    const mockValues = new Uint8Array(32).fill(0xab)
    vi.stubGlobal('crypto', { getRandomValues: (arr: Uint8Array) => { arr.set(mockValues); return arr } })

    const wrapper = await mountComponent()
    await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
    await wrapper.find('[data-testid="generate-secret-btn"]').trigger('click')

    const secretInput = wrapper.find('[data-testid="trigger-secret"]').element as HTMLInputElement
    expect(secretInput.value).toHaveLength(64) // 32 bytes hex
    expect(secretInput.value).toBe('ab'.repeat(32))

    vi.unstubAllGlobals()
  })

  it('shows delete confirmation modal', async () => {
    mockFetchTriggers.mockResolvedValue([
      { id: 't1', name: 'Deletable', source: 'jira', enabled: true, has_secret: false, filters: {}, actions: {}, profile_id: null, task_prompt: null },
    ])
    const wrapper = await mountComponent()

    // Click on trigger to open edit form
    await wrapper.find('[data-testid="trigger-row"]').trigger('click')
    await flushPromises()

    // Click delete
    await wrapper.find('[data-testid="trigger-delete-btn"]').trigger('click')
    expect(wrapper.find('[data-testid="delete-confirm-modal"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Deletable')
  })

  it('toggles trigger enabled state', async () => {
    mockFetchTriggers.mockResolvedValue([
      { id: 't1', name: 'Toggle Me', source: 'jira', enabled: true, has_secret: false, filters: {}, actions: {}, profile_id: null, task_prompt: null },
    ])
    const wrapper = await mountComponent()

    const toggle = wrapper.find('[data-testid="trigger-toggle-t1"]')
    await toggle.trigger('change')
    await flushPromises()

    expect(mockUpdateTrigger).toHaveBeenCalledWith('t1', { enabled: false })
  })

  describe('GitHub source', () => {
    beforeEach(() => {
      mockFetchGithubStatus.mockResolvedValue({ status: 'connected' })
    })

    it('shows GitHub as a source option', async () => {
      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')

      const sourceSelect = wrapper.find('[data-testid="trigger-source"]')
      const options = sourceSelect.findAll('option')
      const values = options.map((o) => o.attributes('value'))
      expect(values).toContain('github')
    })

    it('shows GitHub filter fields when source is github', async () => {
      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')

      // Switch source to github
      await wrapper.find('[data-testid="trigger-source"]').setValue('github')
      await flushPromises()

      expect(wrapper.find('[data-testid="github-org"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="github-project-number"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="introspect-btn"]').exists()).toBe(true)
    })

    it('hides Jira filters when source is github', async () => {
      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
      await wrapper.find('[data-testid="trigger-source"]').setValue('github')
      await flushPromises()

      expect(wrapper.find('[data-testid="trigger-labels"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="trigger-projects"]').exists()).toBe(false)
    })

    it('introspect button is disabled without org and project number', async () => {
      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
      await wrapper.find('[data-testid="trigger-source"]').setValue('github')
      await flushPromises()

      const btn = wrapper.find('[data-testid="introspect-btn"]')
      expect(btn.attributes('disabled')).toBeDefined()
    })

    it('introspect button enabled when org and project number filled', async () => {
      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
      await wrapper.find('[data-testid="trigger-source"]').setValue('github')
      await wrapper.find('[data-testid="github-org"]').setValue('acme-corp')
      await wrapper.find('[data-testid="github-project-number"]').setValue('5')
      await flushPromises()

      const btn = wrapper.find('[data-testid="introspect-btn"]')
      expect(btn.attributes('disabled')).toBeUndefined()
    })

    it('calls introspect and populates status options', async () => {
      mockIntrospectProject.mockResolvedValue({
        project_node_id: 'PVT_abc123',
        title: 'My Project',
        status_field: {
          field_id: 'PVTSSF_field1',
          options: [
            { id: 'opt1', name: 'Todo' },
            { id: 'opt2', name: 'In Progress' },
            { id: 'opt3', name: 'Done' },
          ],
        },
      })

      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
      await wrapper.find('[data-testid="trigger-source"]').setValue('github')
      await wrapper.find('[data-testid="github-org"]').setValue('acme-corp')
      await wrapper.find('[data-testid="github-project-number"]').setValue('5')
      await flushPromises()

      await wrapper.find('[data-testid="introspect-btn"]').trigger('click')
      await flushPromises()

      expect(mockIntrospectProject).toHaveBeenCalledWith('acme-corp', 5)
      expect(toastMock.success).toHaveBeenCalledWith('Project "My Project" introspected')

      // Status dropdowns should appear
      expect(wrapper.find('[data-testid="github-trigger-column"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="github-column-running"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="github-column-complete"]').exists()).toBe(true)
    })

    it('shows introspect error on failure', async () => {
      mockIntrospectProject.mockRejectedValue(new Error('Project not found'))

      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
      await wrapper.find('[data-testid="trigger-source"]').setValue('github')
      await wrapper.find('[data-testid="github-org"]').setValue('acme-corp')
      await wrapper.find('[data-testid="github-project-number"]').setValue('5')
      await flushPromises()

      await wrapper.find('[data-testid="introspect-btn"]').trigger('click')
      await flushPromises()

      expect(toastMock.error).toHaveBeenCalledWith('Project not found')
    })

    it('creates github trigger with correct filters and actions', async () => {
      mockIntrospectProject.mockResolvedValue({
        project_node_id: 'PVT_abc123',
        title: 'My Project',
        status_field: {
          field_id: 'PVTSSF_field1',
          options: [
            { id: 'opt1', name: 'Todo' },
            { id: 'opt2', name: 'In Progress' },
            { id: 'opt3', name: 'Done' },
          ],
        },
      })

      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="add-trigger-btn"]').trigger('click')
      await wrapper.find('[data-testid="trigger-source"]').setValue('github')
      await wrapper.find('[data-testid="trigger-name"]').setValue('GitHub Issues')
      await wrapper.find('[data-testid="github-org"]').setValue('acme-corp')
      await wrapper.find('[data-testid="github-project-number"]').setValue('5')
      await flushPromises()

      // Introspect
      await wrapper.find('[data-testid="introspect-btn"]').trigger('click')
      await flushPromises()

      // Select trigger column
      await wrapper.find('[data-testid="github-trigger-column"]').setValue('Todo')

      // Select column on running
      await wrapper.find('[data-testid="github-column-running"]').setValue('In Progress')

      // Select column on complete
      await wrapper.find('[data-testid="github-column-complete"]').setValue('Done')

      // Save
      await wrapper.find('[data-testid="trigger-save-btn"]').trigger('click')
      await flushPromises()

      expect(mockCreateTrigger).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'GitHub Issues',
          source: 'github',
          filters: expect.objectContaining({
            project_node_id: 'PVT_abc123',
            trigger_column: 'Todo',
            content_types: ['Issue'],
          }),
          actions: expect.objectContaining({
            column_on_running: 'In Progress',
            column_on_complete: 'Done',
            project_field_id: 'PVTSSF_field1',
            column_options: { Todo: 'opt1', 'In Progress': 'opt2', Done: 'opt3' },
          }),
        }),
      )
    })

    it('populates form when editing a github trigger', async () => {
      mockFetchTriggers.mockResolvedValue([
        {
          id: 'gt1',
          name: 'GitHub Trigger',
          source: 'github',
          enabled: true,
          has_secret: false,
          profile_id: null,
          task_prompt: null,
          filters: {
            project_node_id: 'PVT_abc',
            trigger_column: 'Ready',
            content_types: ['Issue', 'PullRequest'],
          },
          actions: {
            add_comment: true,
            column_on_running: 'Working',
            column_on_complete: 'Done',
            copilot_review: true,
            project_field_id: 'PVTSSF_f1',
            column_options: { Ready: 'o1', Working: 'o2', Done: 'o3' },
          },
        },
      ])

      const wrapper = await mountComponent()
      await wrapper.find('[data-testid="trigger-row"]').trigger('click')
      await flushPromises()

      // GitHub filter fields should be visible
      expect(wrapper.find('[data-testid="github-trigger-column"]').exists()).toBe(true)

      // Trigger column should be populated
      const triggerCol = wrapper.find('[data-testid="github-trigger-column"]').element as HTMLSelectElement
      expect(triggerCol.value).toBe('Ready')
    })
  })
})
