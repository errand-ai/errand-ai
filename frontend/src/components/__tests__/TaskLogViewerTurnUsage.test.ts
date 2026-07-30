/**
 * Integration guard for the turn-usage badge.
 *
 * Mounts the real `TaskLogViewer` from the installed `@errand-ai/ui-components`
 * — not a stub — and feeds it a log stream captured verbatim from a real task
 * run against the local stack. The component's own rendering is covered by the
 * library's suite; what this asserts is the seam between the two repos, which
 * neither suite sees on its own: that the fields the task runner actually emits
 * are the fields the released component actually reads.
 *
 * That seam is where this feature failed twice before it worked. The first real
 * run reported `input_tokens: 0` for every turn, and a pin left at ^0.16.0 would
 * render the events as empty elements.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { TaskLogViewer } from '@errand-ai/ui-components'

// Captured from task f2b7ed73 (claude-haiku-4-5 via LiteLLM). Two turns, with
// context climbing 5,530 -> 5,925 tokens across them.
const REAL_LOG = [
  { type: 'llm_turn_start', data: { turn_id: '62ef2b0a', model: 'claude-haiku-4-5-20251001' } },
  { type: 'tool_call', data: { turn_id: '62ef2b0a', tool: 'execute_command', args: { command: 'ls /workspace' } } },
  { type: 'tool_result', data: { turn_id: '62ef2b0a', tool: 'execute_command', output: 'mcp.json\nprompt.txt', length: 19 } },
  { type: 'llm_turn_end', data: { turn_id: '62ef2b0a', duration_ms: 3303, input_tokens: 5530, output_tokens: 343, total_tokens: 5873, cached_tokens: 0 } },
  { type: 'llm_turn_start', data: { turn_id: '9e8a5e12', model: 'claude-haiku-4-5-20251001' } },
  { type: 'llm_turn_end', data: { turn_id: '9e8a5e12', duration_ms: 2041, input_tokens: 5925, output_tokens: 87, total_tokens: 6012, cached_tokens: 0 } },
]
  .map((e) => JSON.stringify(e))
  .join('\n')

async function mountWithLog(logData: string) {
  const wrapper = mount(TaskLogViewer, { props: { mode: 'static', logData } })
  // Entries are pushed during onMounted; the DOM reflects them a tick later.
  await nextTick()
  return wrapper
}

describe('turn usage badge', () => {
  it('renders the measured token count for each turn', async () => {
    const wrapper = await mountWithLog(REAL_LOG)

    const badges = wrapper.findAll('[data-testid="turn-usage"]')
    expect(badges).toHaveLength(2)
    expect(badges[0].text()).toContain('5.5k tokens')
    expect(badges[1].text()).toContain('5.9k tokens')
  })

  it('renders the turn duration alongside the count', async () => {
    const wrapper = await mountWithLog(REAL_LOG)

    const badges = wrapper.findAll('[data-testid="turn-usage"]')
    expect(badges[0].text()).toContain('3.3s')
    expect(badges[1].text()).toContain('2.0s')
  })

  it('shows context climbing across turns, which is the signal', async () => {
    const wrapper = await mountWithLog(REAL_LOG)

    const texts = wrapper.findAll('[data-testid="turn-usage"]').map((b) => b.text())
    expect(texts[0]).not.toEqual(texts[1])
  })

  it('leaves llm_turn_end out of the rendered entries', async () => {
    // Before the library handled it, this event fell through to the flat
    // renderer and drew an empty element once per turn.
    const wrapper = await mountWithLog(REAL_LOG)

    expect(wrapper.html()).not.toContain('llm_turn_end')
  })

  it('renders a turn with no usage exactly as before, with no placeholder number', async () => {
    const noUsage = JSON.stringify({
      type: 'llm_turn_start',
      data: { turn_id: 'aaa', model: 'claude-haiku-4-5-20251001' },
    })

    const wrapper = await mountWithLog(noUsage)

    expect(wrapper.find('[data-testid="turn-separator"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="turn-usage"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('0 tokens')
  })

  it('omits the token figure when the provider reported no usage', async () => {
    // The runner omits the token fields rather than sending zeros, so the badge
    // must cope with a usage event carrying only a duration.
    const durationOnly = [
      { type: 'llm_turn_start', data: { turn_id: 'bbb', model: 'm' } },
      { type: 'llm_turn_end', data: { turn_id: 'bbb', duration_ms: 1200 } },
    ]
      .map((e) => JSON.stringify(e))
      .join('\n')

    const wrapper = await mountWithLog(durationOnly)

    expect(wrapper.text()).not.toContain('tokens')
    expect(wrapper.text()).not.toContain('0 tokens')
  })
})
