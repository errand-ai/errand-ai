import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskOutputModal from '../TaskOutputModal.vue'

describe('TaskOutputModal', () => {
  it('displays the task title as header', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Fix auth bug', output: 'Some output' },
    })
    expect(wrapper.text()).toContain('Fix auth bug')
  })

  it('renders output as markdown HTML in a prose container', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'Line 1\nLine 2\nLine 3' },
    })
    const prose = wrapper.find('.prose')
    expect(prose.exists()).toBe(true)
    expect(prose.text()).toContain('Line 1')
    expect(prose.text()).toContain('Line 3')
  })

  it('shows "No output available" when output is null', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: null },
    })
    expect(wrapper.find('.prose').exists()).toBe(false)
    expect(wrapper.text()).toContain('No output available')
  })

  it('shows "No output available" when output is empty string', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: '' },
    })
    expect(wrapper.find('.prose').exists()).toBe(false)
    expect(wrapper.text()).toContain('No output available')
  })

  it('emits close when Close button is clicked', async () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'output' },
    })
    const closeBtn = wrapper.findAll('button').find((b) => b.text() === 'Close')!
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('emits close when X button is clicked', async () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'output' },
    })
    const xBtn = wrapper.find('button[aria-label="Close"]')
    await xBtn.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('renders markdown headings, lists, and horizontal rules as HTML', () => {
    const md = '# Heading\n\n- Item 1\n- Item 2\n\n---\n'
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: md },
    })
    const prose = wrapper.find('.prose')
    expect(prose.find('h1').exists()).toBe(true)
    expect(prose.find('h1').text()).toBe('Heading')
    expect(prose.find('ul').exists()).toBe(true)
    expect(prose.findAll('li')).toHaveLength(2)
    expect(prose.find('hr').exists()).toBe(true)
  })

  it('renders markdown code blocks as pre>code elements', () => {
    const md = '```\nconsole.log("hello")\n```'
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: md },
    })
    const prose = wrapper.find('.prose')
    expect(prose.find('pre code').exists()).toBe(true)
    expect(prose.find('pre code').text()).toContain('console.log("hello")')
  })

  it('renders plain text output without artifacts', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'Just plain text here' },
    })
    const prose = wrapper.find('.prose')
    expect(prose.exists()).toBe(true)
    expect(prose.text()).toContain('Just plain text here')
    // No markdown-specific elements created
    expect(prose.find('h1').exists()).toBe(false)
    expect(prose.find('ul').exists()).toBe(false)
    expect(prose.find('hr').exists()).toBe(false)
  })

  it('sanitizes dangerous HTML tags from output', () => {
    const malicious = '<script>alert("xss")</script><p>Safe content</p>'
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: malicious },
    })
    const prose = wrapper.find('.prose')
    expect(prose.html()).not.toContain('<script>')
    expect(prose.text()).toContain('Safe content')
  })

  it('uses responsive width classes', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'output' },
    })
    const inner = wrapper.find('dialog > div')
    expect(inner.classes()).toContain('w-[90vw]')
    expect(inner.classes()).toContain('max-w-5xl')
  })

  // --- Copy raw button ---

  it('shows Copy raw button when output is present', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'Some output' },
    })
    const copyBtn = wrapper.find('[data-testid="copy-raw-button"]')
    expect(copyBtn.exists()).toBe(true)
    expect(copyBtn.text()).toBe('Copy raw')
  })

  it('hides Copy raw button when output is null', () => {
    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: null },
    })
    const copyBtn = wrapper.find('[data-testid="copy-raw-button"]')
    expect(copyBtn.exists()).toBe(false)
  })

  it('copies output to clipboard and shows Copied!', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    const wrapper = mount(TaskOutputModal, {
      props: { title: 'Task', output: 'Raw text here' },
    })

    const copyBtn = wrapper.find('[data-testid="copy-raw-button"]')
    await copyBtn.trigger('click')

    expect(writeText).toHaveBeenCalledWith('Raw text here')
    expect(copyBtn.text()).toBe('Copied!')
  })
})
