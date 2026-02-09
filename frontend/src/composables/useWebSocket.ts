import { ref, type Ref } from 'vue'

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected'

export interface UseWebSocketOptions {
  onMessage: (data: unknown) => void
  getToken: () => string | null
}

export interface UseWebSocketReturn {
  status: Ref<WebSocketStatus>
  connect: () => void
  disconnect: () => void
}

const INITIAL_RETRY_MS = 1000
const MAX_RETRY_MS = 30000

function buildWsUrl(token: string): string {
  const loc = window.location
  const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${loc.host}/api/ws/tasks?token=${encodeURIComponent(token)}`
}

export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
  const status = ref<WebSocketStatus>('disconnected')
  let ws: WebSocket | null = null
  let retryMs = INITIAL_RETRY_MS
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let intentionalClose = false

  function connect() {
    const token = options.getToken()
    if (!token) {
      status.value = 'disconnected'
      return
    }

    intentionalClose = false
    status.value = 'connecting'

    try {
      ws = new WebSocket(buildWsUrl(token))
    } catch {
      status.value = 'disconnected'
      scheduleRetry()
      return
    }

    ws.onopen = () => {
      status.value = 'connected'
      retryMs = INITIAL_RETRY_MS
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.event === 'ping') return
        options.onMessage(data)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      status.value = 'disconnected'
      ws = null
      if (!intentionalClose) {
        scheduleRetry()
      }
    }

    ws.onerror = () => {
      // onclose will fire after onerror
    }
  }

  function disconnect() {
    intentionalClose = true
    if (retryTimer) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    status.value = 'disconnected'
  }

  function scheduleRetry() {
    if (retryTimer) return
    retryTimer = setTimeout(() => {
      retryTimer = null
      retryMs = Math.min(retryMs * 2, MAX_RETRY_MS)
      connect()
    }, retryMs)
  }

  return { status, connect, disconnect }
}
