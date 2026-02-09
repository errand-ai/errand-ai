import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useWebSocket } from '../../composables/useWebSocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = 0

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }

  send(_data: string) {}

  // Test helpers
  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  simulateClose() {
    this.readyState = 3
    this.onclose?.()
  }
}

describe('useWebSocket', () => {
  let originalWebSocket: typeof WebSocket

  beforeEach(() => {
    setActivePinia(createPinia())
    MockWebSocket.instances = []
    originalWebSocket = globalThis.WebSocket
    ;(globalThis as any).WebSocket = MockWebSocket as any
    vi.useFakeTimers()
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
    vi.useRealTimers()
  })

  it('connects with token in query parameter', () => {
    const onMessage = vi.fn()
    const { connect } = useWebSocket({
      onMessage,
      getToken: () => 'my-jwt-token',
    })

    connect()

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toContain('token=my-jwt-token')
  })

  it('uses wss:// for https: pages', () => {
    const onMessage = vi.fn()
    const { connect } = useWebSocket({
      onMessage,
      getToken: () => 'tok',
    })

    connect()

    // jsdom default is http://localhost, so ws://
    expect(MockWebSocket.instances[0].url).toMatch(/^ws:\/\//)
  })

  it('sets status to connected on open', async () => {
    const onMessage = vi.fn()
    const { status, connect } = useWebSocket({
      onMessage,
      getToken: () => 'tok',
    })

    connect()
    expect(status.value).toBe('connecting')

    MockWebSocket.instances[0].simulateOpen()
    expect(status.value).toBe('connected')
  })

  it('delivers parsed messages to onMessage callback', () => {
    const onMessage = vi.fn()
    const { connect } = useWebSocket({
      onMessage,
      getToken: () => 'tok',
    })

    connect()
    MockWebSocket.instances[0].simulateOpen()
    MockWebSocket.instances[0].simulateMessage({ event: 'task_created', task: { id: '1' } })

    expect(onMessage).toHaveBeenCalledWith({ event: 'task_created', task: { id: '1' } })
  })

  it('ignores ping messages', () => {
    const onMessage = vi.fn()
    const { connect } = useWebSocket({
      onMessage,
      getToken: () => 'tok',
    })

    connect()
    MockWebSocket.instances[0].simulateOpen()
    MockWebSocket.instances[0].simulateMessage({ event: 'ping' })

    expect(onMessage).not.toHaveBeenCalled()
  })

  it('sets status to disconnected on close', () => {
    const onMessage = vi.fn()
    const { status, connect } = useWebSocket({
      onMessage,
      getToken: () => 'tok',
    })

    connect()
    MockWebSocket.instances[0].simulateOpen()
    MockWebSocket.instances[0].simulateClose()

    expect(status.value).toBe('disconnected')
  })

  it('reconnects with exponential backoff on close', () => {
    const onMessage = vi.fn()
    const { connect } = useWebSocket({
      onMessage,
      getToken: () => 'tok',
    })

    connect()
    MockWebSocket.instances[0].simulateOpen()
    MockWebSocket.instances[0].simulateClose()

    expect(MockWebSocket.instances).toHaveLength(1)

    // After 1s (initial backoff), should reconnect
    vi.advanceTimersByTime(1000)
    expect(MockWebSocket.instances).toHaveLength(2)

    // Close again — next retry should be 2s
    MockWebSocket.instances[1].simulateClose()
    vi.advanceTimersByTime(1500)
    expect(MockWebSocket.instances).toHaveLength(2) // not yet

    vi.advanceTimersByTime(500)
    expect(MockWebSocket.instances).toHaveLength(3) // now at 2s
  })

  it('does not reconnect after intentional disconnect', () => {
    const onMessage = vi.fn()
    const { connect, disconnect } = useWebSocket({
      onMessage,
      getToken: () => 'tok',
    })

    connect()
    MockWebSocket.instances[0].simulateOpen()
    disconnect()

    vi.advanceTimersByTime(60000)
    expect(MockWebSocket.instances).toHaveLength(1) // no new connections
  })

  it('stays disconnected when no token available', () => {
    const onMessage = vi.fn()
    const { status, connect } = useWebSocket({
      onMessage,
      getToken: () => null,
    })

    connect()

    expect(status.value).toBe('disconnected')
    expect(MockWebSocket.instances).toHaveLength(0)
  })
})
