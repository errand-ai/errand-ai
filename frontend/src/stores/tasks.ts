import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { fetchTasks, createTask, updateTask as apiUpdateTask, deleteTask as apiDeleteTask, type TaskData, type TaskStatus } from '../composables/useApi'
import { useAuthStore } from './auth'

const POLL_INTERVAL = 5000
const INITIAL_BACKOFF = 1000
const MAX_BACKOFF = 30000

export type CloudConnectionStatus = 'not_configured' | 'connected' | 'disconnected' | 'error'
export type EventStreamStatus = 'connecting' | 'connected' | 'disconnected'

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<TaskData[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const cloudStatus = ref<CloudConnectionStatus>('not_configured')
  const cloudStorageChanged = ref(0)
  const sseStatus = ref<EventStreamStatus>('disconnected')
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let backoff = INITIAL_BACKOFF
  let intentionalClose = false

  const auth = useAuthStore()

  // --- SSE integration ---

  function handleSseEvent(msg: { event: string; task?: TaskData; status?: string }) {
    if (!msg?.event) return

    // Handle cloud status events (status is nested under "task" key from publish_event)
    if (msg.event === 'cloud_status') {
      const taskObj = msg.task as unknown as Record<string, unknown> | undefined
      const status = msg.status ?? taskObj?.status
      cloudStatus.value = (status as CloudConnectionStatus) ?? 'disconnected'
      return
    }

    if (msg.event === 'cloud_storage_connected' || msg.event === 'cloud_storage_error') {
      cloudStorageChanged.value++
      return
    }

    if (!msg?.task) return

    if (msg.event === 'task_created') {
      const exists = tasks.value.some((t) => t.id === msg.task!.id)
      if (!exists) {
        tasks.value = [...tasks.value, msg.task]
      }
    } else if (msg.event === 'task_updated') {
      tasks.value = tasks.value.map((t) =>
        t.id === msg.task!.id ? msg.task! : t
      )
    } else if (msg.event === 'task_deleted') {
      tasks.value = tasks.value.filter((t) => t.id !== msg.task!.id)
    }
  }

  function sseConnect() {
    const token = auth.token
    if (!token) {
      sseStatus.value = 'disconnected'
      return
    }

    intentionalClose = false
    sseStatus.value = 'connecting'

    const url = `/api/events?token=${encodeURIComponent(token)}`
    eventSource = new EventSource(url)

    eventSource.onopen = () => {
      sseStatus.value = 'connected'
      backoff = INITIAL_BACKOFF
      stopPolling()
    }

    // Handle named SSE events
    const eventTypes = ['task_created', 'task_updated', 'task_deleted', 'cloud_status', 'cloud_storage_connected', 'cloud_storage_error']
    for (const eventType of eventTypes) {
      eventSource.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          handleSseEvent({ event: eventType, ...data })
        } catch {
          // Ignore malformed events
        }
      })
    }

    eventSource.onerror = () => {
      eventSource?.close()
      eventSource = null
      sseStatus.value = 'disconnected'

      if (!intentionalClose) {
        startPolling()
        scheduleReconnect()
      }
    }
  }

  function sseDisconnect() {
    intentionalClose = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    sseStatus.value = 'disconnected'
  }

  function scheduleReconnect() {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      backoff = Math.min(backoff * 2, MAX_BACKOFF)
      sseConnect()
    }, backoff)
  }

  // Watch SSE status for polling fallback
  watch(sseStatus, (newStatus: EventStreamStatus) => {
    if (newStatus === 'connected') {
      stopPolling()
    } else if (newStatus === 'disconnected') {
      startPolling()
    }
  })

  // --- Core data operations ---

  function tasksByStatus(status: TaskStatus): TaskData[] {
    const filtered = tasks.value.filter((t) => t.status === status)
    if (status === 'scheduled') {
      // Scheduled column: sort by execute_at ascending, nulls last
      return filtered.sort((a, b) => {
        if (!a.execute_at && !b.execute_at) return 0
        if (!a.execute_at) return 1
        if (!b.execute_at) return -1
        return new Date(a.execute_at).getTime() - new Date(b.execute_at).getTime()
      })
    }
    if (status === 'completed') {
      // Completed column: most recently completed first (updated_at descending)
      return filtered.sort((a, b) => {
        return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      })
    }
    // All other columns: sort by position ascending, tie-break by created_at ascending
    return filtered.sort((a, b) => {
      if (a.position !== b.position) return a.position - b.position
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    })
  }

  async function load() {
    loading.value = true
    try {
      tasks.value = await fetchTasks()
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load tasks'
    } finally {
      loading.value = false
    }
  }

  async function addTask(input: string) {
    try {
      await createTask(input)
      error.value = null
      await load()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create task'
      throw e
    }
  }

  async function updateTask(id: string, data: { title?: string; description?: string; status?: TaskStatus; position?: number; tags?: string[]; category?: string; execute_at?: string; repeat_interval?: string; repeat_until?: string; profile_id?: string | null }) {
    try {
      await apiUpdateTask(id, data)
      error.value = null
      await load()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update task'
      throw e
    }
  }

  async function removeTask(id: string) {
    try {
      await apiDeleteTask(id)
      tasks.value = tasks.value.filter((t) => t.id !== id)
      error.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete task'
      throw e
    }
  }

  // --- Polling (fallback) ---

  function startPolling() {
    if (pollTimer) return
    load()
    pollTimer = setInterval(load, POLL_INTERVAL)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // --- Lifecycle ---

  function start() {
    load()
    sseConnect()
  }

  function stop() {
    sseDisconnect()
    stopPolling()
  }

  return { tasks, loading, error, sseStatus, cloudStatus, cloudStorageChanged, tasksByStatus, load, addTask, updateTask, removeTask, start, stop, startPolling, stopPolling }
})
