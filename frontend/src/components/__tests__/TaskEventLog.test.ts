import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskEventLog from '../TaskEventLog.vue'
import type { TaskEvent } from '../TaskEventLog.vue'

describe('TaskEventLog', () => {
  // --- Event type rendering ---

  it('renders agent_start event', () => {
    const events: TaskEvent[] = [
      { type: 'agent_start', data: { agent: 'TaskRunner' }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-agent-start"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Agent started')
  })

  it('renders agent_end event', () => {
    const events: TaskEvent[] = [
      { type: 'agent_end', data: { output: { status: 'completed' } }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-agent-end"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Agent completed')
  })

  it('renders thinking event with italic text', () => {
    const events: TaskEvent[] = [
      { type: 'thinking', data: { text: 'Let me consider.' }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-thinking"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Let me consider.')

    const textDiv = el.find('.whitespace-pre-wrap')
    expect(textDiv.classes()).toContain('italic')
  })

  it('renders reasoning event with purple border', () => {
    const events: TaskEvent[] = [
      { type: 'reasoning', data: { text: 'Step 1: Analyze.' }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-reasoning"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('Step 1: Analyze.')
    expect(el.classes()).toContain('border-purple-500')
  })

  it('renders tool_call event with tool name in header', () => {
    const events: TaskEvent[] = [
      { type: 'tool_call', data: { tool: 'execute_command', args: { command: 'ls -la' } }, collapsed: true },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-tool-call"]')
    expect(el.exists()).toBe(true)

    const header = el.find('[data-testid="tool-call-header"]')
    expect(header.text()).toContain('execute_command')
    expect(header.text()).toContain('ls -la')
  })

  it('renders error event with red styling', () => {
    const events: TaskEvent[] = [
      { type: 'error', data: { message: 'API auth failed' }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-error"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('API auth failed')
    expect(el.classes()).toContain('bg-red-900/50')
  })

  it('renders raw event with monospace text', () => {
    const events: TaskEvent[] = [
      { type: 'raw', data: { line: 'some debug output' }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-raw"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toContain('some debug output')
    expect(el.classes()).toContain('font-mono')
  })

  // --- Collapse toggle for thinking/reasoning ---

  it('collapses thinking events exceeding 3 lines and shows toggle', () => {
    const longText = 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5'
    const events: TaskEvent[] = [
      { type: 'thinking', data: { text: longText }, collapsed: true },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const el = wrapper.find('[data-testid="event-thinking"]')
    const textDiv = el.find('.whitespace-pre-wrap')
    expect(textDiv.classes()).toContain('line-clamp-3')

    const toggle = el.find('[data-testid="toggle-collapse"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toBe('Show more')
  })

  it('does not show toggle for short thinking events', () => {
    const events: TaskEvent[] = [
      { type: 'thinking', data: { text: 'Short thought.' }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const toggle = wrapper.find('[data-testid="toggle-collapse"]')
    expect(toggle.exists()).toBe(false)
  })

  it('toggles thinking collapse on click', async () => {
    const longText = 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5'
    const events: TaskEvent[] = [
      { type: 'thinking', data: { text: longText }, collapsed: true },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const toggle = wrapper.find('[data-testid="toggle-collapse"]')
    expect(toggle.text()).toBe('Show more')

    await toggle.trigger('click')
    expect(toggle.text()).toBe('Show less')

    const textDiv = wrapper.find('[data-testid="event-thinking"] .whitespace-pre-wrap')
    expect(textDiv.classes()).not.toContain('line-clamp-3')
  })

  it('collapses reasoning events exceeding 3 lines', () => {
    const longText = 'Step 1\nStep 2\nStep 3\nStep 4\nStep 5'
    const events: TaskEvent[] = [
      { type: 'reasoning', data: { text: longText }, collapsed: true },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const toggle = wrapper.find('[data-testid="event-reasoning"] [data-testid="toggle-collapse"]')
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toBe('Show more')
  })

  // --- Tool call expand/collapse ---

  it('tool_call cards hide args when collapsed', () => {
    const events: TaskEvent[] = [
      { type: 'tool_call', data: { tool: 'execute_command', args: { command: 'git status' } }, collapsed: true },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const argsBody = wrapper.find('[data-testid="tool-call-args"]')
    expect(argsBody.exists()).toBe(false)
  })

  it('expands tool_call card on header click', async () => {
    const events: TaskEvent[] = [
      { type: 'tool_call', data: { tool: 'execute_command', args: { command: 'git status' } }, collapsed: true },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const header = wrapper.find('[data-testid="tool-call-header"]')
    await header.trigger('click')

    const argsBody = wrapper.find('[data-testid="tool-call-args"]')
    expect(argsBody.exists()).toBe(true)
    expect(argsBody.text()).toContain('git status')
  })

  it('renders tool_result section when present on tool_call', () => {
    const events: TaskEvent[] = [
      {
        type: 'tool_call',
        data: { tool: 'execute_command', args: { command: 'ls' } },
        collapsed: true,
        result: { output: 'file1.txt\nfile2.txt', length: 21, collapsed: false },
      },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    const resultSection = wrapper.find('[data-testid="tool-result-section"]')
    expect(resultSection.exists()).toBe(true)
    expect(resultSection.text()).toContain('21 chars')

    const resultOutput = wrapper.find('[data-testid="tool-result-output"]')
    expect(resultOutput.text()).toContain('file1.txt')
  })

  it('renders multiple event types in sequence', () => {
    const events: TaskEvent[] = [
      { type: 'agent_start', data: { agent: 'TaskRunner' }, collapsed: false },
      { type: 'thinking', data: { text: 'Processing...' }, collapsed: false },
      { type: 'tool_call', data: { tool: 'exec', args: { cmd: 'ls' } }, collapsed: true },
      { type: 'error', data: { message: 'Something failed' }, collapsed: false },
      { type: 'raw', data: { line: 'debug line' }, collapsed: false },
      { type: 'agent_end', data: { output: { status: 'done' } }, collapsed: false },
    ]
    const wrapper = mount(TaskEventLog, { props: { events } })

    expect(wrapper.find('[data-testid="event-agent-start"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-thinking"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-tool-call"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-raw"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="event-agent-end"]').exists()).toBe(true)
  })

  it('renders empty when events array is empty', () => {
    const wrapper = mount(TaskEventLog, { props: { events: [] } })
    expect(wrapper.text()).toBe('')
  })
})
