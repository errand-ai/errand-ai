import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TaskForm from '../TaskForm.vue'
import { useTaskStore } from '../../stores/tasks'

// Mock the useApi module
vi.mock('../../composables/useApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../composables/useApi')>()
  return {
    ...actual,
    fetchTranscriptionStatus: vi.fn().mockResolvedValue({ enabled: false }),
    transcribeAudio: vi.fn().mockResolvedValue('Transcribed text'),
  }
})

import { fetchTranscriptionStatus, transcribeAudio } from '../../composables/useApi'

describe('TaskForm', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(fetchTranscriptionStatus).mockResolvedValue({ enabled: false })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('has placeholder text "New task..."', () => {
    const wrapper = mount(TaskForm)
    const input = wrapper.find('input')
    expect(input.attributes('placeholder')).toBe('New task...')
  })

  it('calls store addTask with input text on submission', async () => {
    const wrapper = mount(TaskForm)
    const store = useTaskStore()
    store.addTask = vi.fn().mockResolvedValue(undefined)

    await wrapper.find('input').setValue('New task')
    await wrapper.find('form').trigger('submit')

    expect(store.addTask).toHaveBeenCalledWith('New task')
  })

  it('shows validation error for empty input without calling store', async () => {
    const wrapper = mount(TaskForm)
    const store = useTaskStore()
    store.addTask = vi.fn()

    await wrapper.find('form').trigger('submit')

    expect(wrapper.text()).toContain('Task cannot be empty')
    expect(store.addTask).not.toHaveBeenCalled()
  })

  it('clears input after successful submission', async () => {
    const wrapper = mount(TaskForm)
    const store = useTaskStore()
    store.addTask = vi.fn().mockResolvedValue(undefined)

    await wrapper.find('input').setValue('New task')
    await wrapper.find('form').trigger('submit')

    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('')
  })

  // --- 9.1 Microphone button visibility ---

  it('hides microphone button when transcription is disabled', async () => {
    vi.mocked(fetchTranscriptionStatus).mockResolvedValue({ enabled: false })

    const wrapper = mount(TaskForm)
    await flushPromises()

    expect(wrapper.find('[data-testid="mic-button"]').exists()).toBe(false)
  })

  it('shows microphone button when MediaRecorder is available AND transcription is enabled', async () => {
    vi.mocked(fetchTranscriptionStatus).mockResolvedValue({ enabled: true })

    // Mock MediaRecorder
    const originalMediaRecorder = globalThis.MediaRecorder
    globalThis.MediaRecorder = vi.fn() as any

    const wrapper = mount(TaskForm)
    await flushPromises()

    expect(wrapper.find('[data-testid="mic-button"]').exists()).toBe(true)

    globalThis.MediaRecorder = originalMediaRecorder
  })

  it('hides microphone button when MediaRecorder is not supported', async () => {
    vi.mocked(fetchTranscriptionStatus).mockResolvedValue({ enabled: true })

    // Remove MediaRecorder
    const originalMediaRecorder = globalThis.MediaRecorder
    // @ts-ignore
    delete globalThis.MediaRecorder

    const wrapper = mount(TaskForm)
    await flushPromises()

    expect(wrapper.find('[data-testid="mic-button"]').exists()).toBe(false)

    globalThis.MediaRecorder = originalMediaRecorder
  })

  // --- 9.2 Recording flow ---

  it('clicking mic button starts recording (state change)', async () => {
    vi.mocked(fetchTranscriptionStatus).mockResolvedValue({ enabled: true })

    const mockStart = vi.fn()
    const originalMediaRecorder = globalThis.MediaRecorder

    // Must use class-style mock for MediaRecorder constructor
    globalThis.MediaRecorder = class MockMediaRecorder {
      start = mockStart
      stop = vi.fn()
      state = 'inactive'
      ondataavailable: any = null
      onstop: any = null
      mimeType = 'audio/webm'
    } as any

    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
      configurable: true,
    })

    const wrapper = mount(TaskForm)
    await flushPromises()

    const micButton = wrapper.find('[data-testid="mic-button"]')
    await micButton.trigger('click')
    await flushPromises()
    // Need extra tick for the async getUserMedia to resolve
    await new Promise(r => setTimeout(r, 0))
    await flushPromises()

    expect(mockStart).toHaveBeenCalled()

    globalThis.MediaRecorder = originalMediaRecorder
  })

  // --- 9.3 Transcript insertion ---

  it('successful transcription appends text to input', async () => {
    vi.mocked(fetchTranscriptionStatus).mockResolvedValue({ enabled: true })
    vi.mocked(transcribeAudio).mockResolvedValue('Buy groceries')

    const originalMediaRecorder = globalThis.MediaRecorder
    let onstopCallback: (() => void) | null = null

    globalThis.MediaRecorder = class MockMediaRecorder {
      start = vi.fn()
      stop() { if (onstopCallback) onstopCallback() }
      state = 'recording'
      ondataavailable: any = null
      get onstop() { return onstopCallback }
      set onstop(fn: any) { onstopCallback = fn }
      mimeType = 'audio/webm'
    } as any

    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
      configurable: true,
    })

    const wrapper = mount(TaskForm)
    await flushPromises()

    // Start recording
    await wrapper.find('[data-testid="mic-button"]').trigger('click')
    await new Promise(r => setTimeout(r, 0))
    await flushPromises()

    // Stop recording - clicking the button again
    await wrapper.find('[data-testid="mic-button"]').trigger('click')
    await new Promise(r => setTimeout(r, 0))
    await flushPromises()

    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('Buy groceries')

    globalThis.MediaRecorder = originalMediaRecorder
  })

  it('error during transcription shows error message', async () => {
    vi.mocked(fetchTranscriptionStatus).mockResolvedValue({ enabled: true })
    vi.mocked(transcribeAudio).mockRejectedValue(new Error('Transcription failed'))

    const originalMediaRecorder = globalThis.MediaRecorder
    let onstopCallback: (() => void) | null = null

    globalThis.MediaRecorder = class MockMediaRecorder {
      start = vi.fn()
      stop() { if (onstopCallback) onstopCallback() }
      state = 'recording'
      ondataavailable: any = null
      get onstop() { return onstopCallback }
      set onstop(fn: any) { onstopCallback = fn }
      mimeType = 'audio/webm'
    } as any

    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
      configurable: true,
    })

    const wrapper = mount(TaskForm)
    await flushPromises()

    // Start recording
    await wrapper.find('[data-testid="mic-button"]').trigger('click')
    await new Promise(r => setTimeout(r, 0))
    await flushPromises()

    // Stop recording
    await wrapper.find('[data-testid="mic-button"]').trigger('click')
    await new Promise(r => setTimeout(r, 0))
    await flushPromises()

    expect(wrapper.text()).toContain('Voice transcription failed')

    globalThis.MediaRecorder = originalMediaRecorder
  })
})
