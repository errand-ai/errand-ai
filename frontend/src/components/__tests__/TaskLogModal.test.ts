import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import TaskLogModal from '../TaskLogModal.vue'
import { useAuthStore } from '../../stores/auth'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  readyState = 1

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close() {
    this.readyState = 3
  }

  simulateMessage(data: string) {
    this.onmessage?.({ data })
  }

  simulateClose() {
    this.readyState = 3
    this.onclose?.()
  }
}

describe('TaskLogModal', () => {
  let originalWebSocket: typeof WebSocket

  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.token = 'test-jwt'

    MockWebSocket.instances = []
    originalWebSocket = globalThis.WebSocket
    ;(globalThis as any).WebSocket = MockWebSocket as any

    // Mock showModal since JSDOM doesn't fully support <dialog>
    HTMLDialogElement.prototype.showModal = vi.fn()
    HTMLDialogElement.prototype.close = vi.fn()
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
  })

  it('connects WebSocket on mount with correct URL', () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toContain('/api/ws/tasks/abc-123/logs')
    expect(MockWebSocket.instances[0].url).toContain('token=test-jwt')

    wrapper.unmount()
  })

  it('disconnects WebSocket on unmount', () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    const closeSpy = vi.spyOn(ws, 'close')

    wrapper.unmount()

    expect(closeSpy).toHaveBeenCalled()
  })

  it('shows "Waiting for logs..." when no lines received', () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    expect(wrapper.text()).toContain('Waiting for logs...')

    wrapper.unmount()
  })

  it('appends log lines from WebSocket messages', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({ event: 'task_log', line: 'Step 1\n' }))
    ws.simulateMessage(JSON.stringify({ event: 'task_log', line: 'Step 2\n' }))
    await flushPromises()

    const logOutput = wrapper.find('[data-testid="log-output"]')
    expect(logOutput.exists()).toBe(true)
    expect(logOutput.text()).toContain('Step 1')
    expect(logOutput.text()).toContain('Step 2')

    wrapper.unmount()
  })

  it('shows task finished indicator on task_log_end', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({ event: 'task_log', line: 'Done\n' }))
    ws.simulateMessage(JSON.stringify({ event: 'task_log_end' }))
    await flushPromises()

    const indicator = wrapper.find('[data-testid="task-finished-indicator"]')
    expect(indicator.exists()).toBe(true)
    expect(indicator.text()).toContain('Task finished')

    wrapper.unmount()
  })

  it('displays the task title in the header', () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'Generate Report' },
    })

    expect(wrapper.text()).toContain('Generate Report')

    wrapper.unmount()
  })

  it('emits close when close button is clicked', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const closeBtn = wrapper.find('button[title="Close"]')
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    wrapper.unmount()
  })
})
