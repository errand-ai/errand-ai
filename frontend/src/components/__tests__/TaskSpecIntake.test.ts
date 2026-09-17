import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TaskSpecIntake from '../TaskSpecIntake.vue'
import type { TaskSpecDraft } from '../../composables/useApi'

const api = vi.hoisted(() => ({
  fetchTaskSpecs: vi.fn(),
  startTaskSpec: vi.fn(),
  answerTaskSpec: vi.fn(),
  confirmTaskSpec: vi.fn(),
  cancelTaskSpec: vi.fn(),
  createTask: vi.fn(),
}))

vi.mock('../../composables/useApi', async () => {
  const actual = await vi.importActual<typeof import('../../composables/useApi')>('../../composables/useApi')
  return { ...actual, ...api }
})

function draft(overrides: Partial<TaskSpecDraft> = {}): TaskSpecDraft {
  return {
    id: 'd1',
    status: 'ready',
    source: 'web',
    input: 'Send me the quarterly numbers',
    questions: [],
    questions_unresolved: false,
    spec_preview: {
      title: 'Quarterly Numbers',
      description: 'Email the Q3 finance numbers to me',
      category: 'immediate',
      execute_at: null,
      repeat_interval: null,
      repeat_until: null,
      profile: null,
    },
    round: 0,
    max_rounds: 2,
    conversation: [
      { role: 'user', content: 'Send me the quarterly numbers', ts: '' },
      { role: 'assistant', content: 'Ready: Quarterly Numbers', ts: '' },
    ],
    created_at: null,
    expires_at: '2026-09-18T00:00:00Z',
    resolved_task_id: null,
    ...overrides,
  }
}

const QUESTIONS = [
  { id: 'source', text: 'Which spreadsheet?', kind: 'free_text' as const },
  { id: 'channel', text: 'Where should they go?', kind: 'choice' as const, choices: ['Email', 'Slack'] },
]

function asking(overrides: Partial<TaskSpecDraft> = {}): TaskSpecDraft {
  return draft({
    status: 'drafting',
    questions: QUESTIONS,
    conversation: [
      { role: 'user', content: 'Send me the quarterly numbers', ts: '' },
      { role: 'assistant', content: 'Which spreadsheet?\nWhere should they go?', ts: '' },
    ],
    ...overrides,
  })
}

async function mountAndStart(first: TaskSpecDraft) {
  api.startTaskSpec.mockResolvedValue(first)
  const wrapper = mount(TaskSpecIntake)
  await flushPromises()
  await wrapper.get('[data-testid="intake-input"]').setValue('Send me the quarterly numbers')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.resetAllMocks()
  api.fetchTaskSpecs.mockResolvedValue([])
})

describe('TaskSpecIntake', () => {
  it('shows a preview for an unambiguous task and creates it on Run', async () => {
    const task = { id: 't1', title: 'Quarterly Numbers' }
    api.confirmTaskSpec.mockResolvedValue(task)
    const wrapper = await mountAndStart(draft())

    expect(api.startTaskSpec).toHaveBeenCalledWith('Send me the quarterly numbers')
    expect(wrapper.find('[data-testid="intake-questions"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="preview-title"]').text()).toBe('Quarterly Numbers')
    expect(wrapper.get('[data-testid="preview-description"]').text()).toBe('Email the Q3 finance numbers to me')

    await wrapper.get('[data-testid="intake-run"]').trigger('click')
    await flushPromises()

    expect(api.confirmTaskSpec).toHaveBeenCalledWith('d1')
    expect(wrapper.emitted('task-created')).toEqual([[task]])
    expect(wrapper.find('[data-testid="intake-draft"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="intake-input"]').element as HTMLTextAreaElement).value).toBe('')
    expect(api.createTask).not.toHaveBeenCalled()
  })

  it('asks questions and sends the answers', async () => {
    api.answerTaskSpec.mockResolvedValue(draft({
      round: 1,
      conversation: [
        ...asking().conversation,
        { role: 'user', content: 'Which spreadsheet? -> Q3', ts: '' },
        { role: 'assistant', content: 'Ready: Quarterly Numbers', ts: '' },
      ],
    }))
    const wrapper = await mountAndStart(asking())

    expect(wrapper.find('[data-testid="intake-preview"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="answer-source"]').element.tagName).toBe('INPUT')
    const select = wrapper.get('[data-testid="answer-channel"]')
    expect(select.element.tagName).toBe('SELECT')
    expect(select.findAll('option').map((o) => o.text())).toEqual(['Choose one', 'Email', 'Slack'])
    expect(wrapper.text()).toContain('round 1 of 2')

    await wrapper.get('[data-testid="answer-source"]').setValue('Q3')
    await select.setValue('Email')
    await wrapper.get('[data-testid="intake-questions"]').trigger('submit')
    await flushPromises()

    expect(api.answerTaskSpec).toHaveBeenCalledWith('d1', { source: 'Q3', channel: 'Email' })
    expect(wrapper.find('[data-testid="intake-preview"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="intake-history"]').text()).toContain('Which spreadsheet? -> Q3')
  })

  it('offers "Just run it" while questions are open', async () => {
    api.confirmTaskSpec.mockResolvedValue({ id: 't1' })
    const wrapper = await mountAndStart(asking())
    await wrapper.get('[data-testid="intake-just-run"]').trigger('click')
    await flushPromises()
    expect(api.confirmTaskSpec).toHaveBeenCalledWith('d1')
    expect(api.answerTaskSpec).not.toHaveBeenCalled()
    expect(wrapper.emitted('task-created')).toHaveLength(1)
  })

  it('shows unresolved questions read-only once the round cap is reached', async () => {
    const wrapper = await mountAndStart(draft({ round: 2, questions: QUESTIONS, questions_unresolved: true }))
    const unresolved = wrapper.get('[data-testid="intake-unresolved"]')
    expect(unresolved.text()).toContain('Which spreadsheet?')
    expect(unresolved.text()).toContain('Where should they go?')
    expect(wrapper.find('[data-testid="answer-source"]').exists()).toBe(false)
    expect(wrapper.find('input, select').exists()).toBe(false)
    expect(wrapper.find('[data-testid="intake-run"]').exists()).toBe(true)
  })

  it('cancels a draft', async () => {
    api.cancelTaskSpec.mockResolvedValue(draft({ status: 'abandoned' }))
    const wrapper = await mountAndStart(asking())
    await wrapper.get('[data-testid="intake-cancel"]').trigger('click')
    await flushPromises()
    expect(api.cancelTaskSpec).toHaveBeenCalledWith('d1')
    expect(wrapper.find('[data-testid="intake-draft"]').exists()).toBe(false)
    expect(wrapper.emitted('task-created')).toBeUndefined()
  })

  it('rejects empty input without calling the API', async () => {
    const wrapper = mount(TaskSpecIntake)
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('[data-testid="form-error"]').text()).toBe('Task cannot be empty')
    expect(api.startTaskSpec).not.toHaveBeenCalled()
  })

  it('resumes the newest pending draft', async () => {
    api.fetchTaskSpecs.mockResolvedValue([asking({ id: 'pending' })])
    const wrapper = mount(TaskSpecIntake)
    await flushPromises()
    expect(wrapper.find('[data-testid="intake-questions"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="intake-original"]').text()).toBe('Send me the quarterly numbers')
  })

  it('drops a draft that has expired or finished elsewhere', async () => {
    const { TaskSpecError } = await vi.importActual<typeof import('../../composables/useApi')>('../../composables/useApi')
    api.confirmTaskSpec.mockRejectedValue(new TaskSpecError('Task draft not found or expired', 404))
    const wrapper = await mountAndStart(draft())
    await wrapper.get('[data-testid="intake-run"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="form-error"]').text()).toBe('Task draft not found or expired')
    expect(wrapper.find('[data-testid="intake-draft"]').exists()).toBe(false)
  })

  it('keeps the draft on other errors', async () => {
    api.answerTaskSpec.mockRejectedValue(new Error('Failed to send answers: 500'))
    const wrapper = await mountAndStart(asking())
    await wrapper.get('[data-testid="intake-questions"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="form-error"]').text()).toBe('Failed to send answers: 500')
    expect(wrapper.find('[data-testid="intake-questions"]').exists()).toBe(true)
  })

  it('passes the voice slot a transcription handler', async () => {
    const wrapper = mount(TaskSpecIntake, {
      slots: {
        voice: `<template #voice="{ onTranscription }"><button data-testid="voice" type="button" @click="onTranscription('from voice')" /></template>`,
      },
    })
    await flushPromises()
    await wrapper.get('[data-testid="voice"]').trigger('click')
    expect((wrapper.get('[data-testid="intake-input"]').element as HTMLTextAreaElement).value).toBe('from voice')
  })
})
