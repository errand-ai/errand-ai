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

    HTMLDialogElement.prototype.showModal = vi.fn()
    HTMLDialogElement.prototype.close = vi.fn()
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
  })

  // --- Connection basics ---

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

  it('shows "Waiting for logs..." when no events received', () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    expect(wrapper.text()).toContain('Waiting for logs...')

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

  // --- 7.1: Structured event rendering for each event type ---

  it('renders agent_start event', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'agent_start',
      data: { agent: 'TaskRunner' },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-agent-start"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Agent started')

    wrapper.unmount()
  })

  it('renders agent_end event', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'agent_end',
      data: { output: { status: 'completed', result: 'Done' } },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-agent-end"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Agent completed')

    wrapper.unmount()
  })

  it('renders thinking event', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'thinking',
      data: { text: 'Let me consider the approach.' },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-thinking"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Let me consider the approach.')

    wrapper.unmount()
  })

  it('renders reasoning event with purple border', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'reasoning',
      data: { text: 'Step 1: Analyze the problem.' },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-reasoning"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Step 1: Analyze the problem.')
    expect(el.classes()).toContain('border-purple-500')

    wrapper.unmount()
  })

  it('renders tool_call event with tool name header', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'ls -la' } },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-tool-call"]')
    expect(el.exists()).toBe(true)

    const header = el.find('[data-testid="tool-call-header"]')
    expect(header.text()).toContain('execute_command')
    expect(header.text()).toContain('ls -la')

    wrapper.unmount()
  })

  it('shows truncated args preview in tool_call header for long commands', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'task-1', title: 'Test' },
    })

    const ws = MockWebSocket.instances[0]
    const longCmd = 'a'.repeat(100)
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: longCmd } },
    }))
    await flushPromises()

    const header = wrapper.find('[data-testid="tool-call-header"]')
    expect(header.text()).toContain('a'.repeat(80) + '...')
    expect(header.text()).not.toContain('a'.repeat(100))

    wrapper.unmount()
  })

  it('renders error event as red alert block', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'error',
      data: { message: 'API auth failed' },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-error"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('API auth failed')
    expect(el.classes()).toContain('bg-red-900/50')

    wrapper.unmount()
  })

  it('renders raw event as monospace text', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'raw',
      data: { line: 'some debug output' },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-raw"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('some debug output')
    expect(el.classes()).toContain('font-mono')

    wrapper.unmount()
  })

  it('shows task finished indicator on task_log_end', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'agent_start',
      data: { agent: 'TaskRunner' },
    }))
    ws.simulateMessage(JSON.stringify({ event: 'task_log_end' }))
    await flushPromises()

    const indicator = wrapper.find('[data-testid="task-finished-indicator"]')
    expect(indicator.exists()).toBe(true)
    expect(indicator.text()).toContain('Task finished')

    wrapper.unmount()
  })

  it('renders multiple events in sequence', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event', type: 'agent_start', data: { agent: 'TaskRunner' },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event', type: 'thinking', data: { text: 'Thinking...' },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event', type: 'tool_call', data: { tool: 'execute_command', args: { command: 'ls' } },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event', type: 'agent_end', data: { output: { status: 'completed' } },
    }))
    await flushPromises()

    expect(wrapper.find('[data-testid="event-agent-start"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-thinking"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-tool-call"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-agent-end"]').exists()).toBe(true)

    wrapper.unmount()
  })

  // --- 7.2: Collapsible behaviour ---

  it('collapses thinking events exceeding 3 lines', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const longText = 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5'
    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'thinking',
      data: { text: longText },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-thinking"]')
    expect(el.exists()).toBe(true)

    // Should have a collapse toggle
    const toggle = el.find('[data-testid="toggle-collapse"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toBe('Show more')

    // The text container should have line-clamp-3
    const textDiv = el.find('.whitespace-pre-wrap')
    expect(textDiv.classes()).toContain('line-clamp-3')

    wrapper.unmount()
  })

  it('does not show collapse toggle for short thinking events', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'thinking',
      data: { text: 'Short thought.' },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-thinking"]')
    expect(el.exists()).toBe(true)

    const toggle = el.find('[data-testid="toggle-collapse"]')
    expect(toggle.exists()).toBe(false)

    wrapper.unmount()
  })

  it('toggles thinking collapse on click', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const longText = 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5'
    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'thinking',
      data: { text: longText },
    }))
    await flushPromises()

    const toggle = wrapper.find('[data-testid="toggle-collapse"]')
    expect(toggle.text()).toBe('Show more')

    await toggle.trigger('click')
    expect(toggle.text()).toBe('Show less')

    // Text should no longer have line-clamp
    const textDiv = wrapper.find('[data-testid="event-thinking"] .whitespace-pre-wrap')
    expect(textDiv.classes()).not.toContain('line-clamp-3')

    wrapper.unmount()
  })

  it('collapses reasoning events exceeding 3 lines', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const longText = 'Step 1\nStep 2\nStep 3\nStep 4\nStep 5'
    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'reasoning',
      data: { text: longText },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-reasoning"]')
    const toggle = el.find('[data-testid="toggle-collapse"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toBe('Show more')

    wrapper.unmount()
  })

  it('does not show collapse toggle for short reasoning events', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'reasoning',
      data: { text: 'Short reasoning.' },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-reasoning"]')
    expect(el.exists()).toBe(true)

    const toggle = el.find('[data-testid="toggle-collapse"]')
    expect(toggle.exists()).toBe(false)

    wrapper.unmount()
  })

  it('collapses long tool_result output by default', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const longOutput = 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5'
    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'ls' } },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_result',
      data: { tool: 'execute_command', output: longOutput, length: longOutput.length },
    }))
    await flushPromises()

    const resultOutput = wrapper.find('[data-testid="tool-result-output"]')
    expect(resultOutput.exists()).toBe(true)
    expect(resultOutput.classes()).toContain('line-clamp-3')

    const toggle = wrapper.find('[data-testid="toggle-result-collapse"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toBe('Show more')

    // Click to expand
    await toggle.trigger('click')
    expect(resultOutput.classes()).not.toContain('line-clamp-3')
    expect(toggle.text()).toBe('Show less')

    wrapper.unmount()
  })

  it('does not collapse short tool_result output', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'pwd' } },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_result',
      data: { tool: 'execute_command', output: '/workspace', length: 10 },
    }))
    await flushPromises()

    const resultOutput = wrapper.find('[data-testid="tool-result-output"]')
    expect(resultOutput.exists()).toBe(true)
    expect(resultOutput.classes()).not.toContain('line-clamp-3')

    const toggle = wrapper.find('[data-testid="toggle-result-collapse"]')
    expect(toggle.exists()).toBe(false)

    wrapper.unmount()
  })

  it('tool_call cards are collapsed by default', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'git status' } },
    }))
    await flushPromises()

    const el = wrapper.find('[data-testid="event-tool-call"]')
    // Args body should not be visible when collapsed
    const argsBody = el.find('[data-testid="tool-call-args"]')
    expect(argsBody.exists()).toBe(false)

    wrapper.unmount()
  })

  it('expands tool_call card on header click', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'git status' } },
    }))
    await flushPromises()

    const header = wrapper.find('[data-testid="tool-call-header"]')
    await header.trigger('click')

    const argsBody = wrapper.find('[data-testid="tool-call-args"]')
    expect(argsBody.exists()).toBe(true)
    expect(argsBody.text()).toContain('git status')

    wrapper.unmount()
  })

  // --- 7.3: tool_result appending to preceding tool_call card ---

  it('appends tool_result to preceding tool_call card', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'ls' } },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_result',
      data: { tool: 'execute_command', output: 'file1.txt\nfile2.txt', length: 21 },
    }))
    await flushPromises()

    // Should have only one event card (tool_call with result appended)
    const toolCards = wrapper.findAll('[data-testid="event-tool-call"]')
    expect(toolCards).toHaveLength(1)

    const resultSection = wrapper.find('[data-testid="tool-result-section"]')
    expect(resultSection.exists()).toBe(true)
    expect(resultSection.text()).toContain('21 chars')

    const resultOutput = wrapper.find('[data-testid="tool-result-output"]')
    expect(resultOutput.exists()).toBe(true)
    expect(resultOutput.text()).toContain('file1.txt')

    wrapper.unmount()
  })

  it('does not append tool_result if tool name does not match', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'ls' } },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_result',
      data: { tool: 'other_tool', output: 'result', length: 6 },
    }))
    await flushPromises()

    // The tool_result should not be appended (tool name mismatch),
    // so no result section on the tool_call card
    const resultSection = wrapper.find('[data-testid="tool-result-section"]')
    expect(resultSection.exists()).toBe(false)

    wrapper.unmount()
  })

  it('shows tool_result section when tool_call card is expanded', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_call',
      data: { tool: 'execute_command', args: { command: 'pwd' } },
    }))
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'tool_result',
      data: { tool: 'execute_command', output: '/workspace', length: 10 },
    }))
    await flushPromises()

    // Result section should be visible even when card is collapsed
    // (result section is outside the collapsible args section)
    const resultSection = wrapper.find('[data-testid="tool-result-section"]')
    expect(resultSection.exists()).toBe(true)
    expect(resultSection.text()).toContain('10 chars')

    wrapper.unmount()
  })

  // --- 7.4: Auto-scroll / manual scroll detection ---

  it('marks finished on WebSocket close', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateClose()
    await flushPromises()

    const indicator = wrapper.find('[data-testid="task-finished-indicator"]')
    expect(indicator.exists()).toBe(true)

    wrapper.unmount()
  })

  it('auto-scrolls log container when new events arrive', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const container = wrapper.find('[data-testid="log-container"]')
    const containerEl = container.element as HTMLElement

    // Mock scrollHeight/clientHeight to simulate scrollable container
    Object.defineProperty(containerEl, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(containerEl, 'clientHeight', { value: 300, configurable: true })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'thinking',
      data: { text: 'Processing...' },
    }))
    await flushPromises()

    // scrollTop should be set to scrollHeight (auto-scroll)
    expect(containerEl.scrollTop).toBe(1000)

    wrapper.unmount()
  })

  it('stops auto-scrolling when user scrolls up', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const container = wrapper.find('[data-testid="log-container"]')
    const containerEl = container.element as HTMLElement

    Object.defineProperty(containerEl, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(containerEl, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(containerEl, 'scrollTop', {
      value: 600,
      writable: true,
      configurable: true,
    })

    // Simulate user scrolling up (scrollHeight - scrollTop - clientHeight > 50)
    await container.trigger('scroll')

    // Now send a new event
    const ws = MockWebSocket.instances[0]
    ws.simulateMessage(JSON.stringify({
      event: 'task_event',
      type: 'thinking',
      data: { text: 'More thinking...' },
    }))
    await flushPromises()

    // scrollTop should NOT be updated to scrollHeight because user scrolled up
    expect(containerEl.scrollTop).toBe(600)

    wrapper.unmount()
  })

  // --- Non-JSON message fallback ---

  it('handles non-JSON WebSocket messages as raw events', async () => {
    const wrapper = mount(TaskLogModal, {
      props: { taskId: 'abc-123', title: 'My Task' },
    })

    const ws = MockWebSocket.instances[0]
    ws.simulateMessage('plain text message')
    await flushPromises()

    const el = wrapper.find('[data-testid="event-raw"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('plain text message')

    wrapper.unmount()
  })
})
