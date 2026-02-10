import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { fetchTasks, createTask, updateTask as apiUpdateTask, deleteTask as apiDeleteTask, type TaskData, type TaskStatus } from '../composables/useApi'
import { useWebSocket, type WebSocketStatus } from '../composables/useWebSocket'
import { useAuthStore } from './auth'

const POLL_INTERVAL = 5000

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<TaskData[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const auth = useAuthStore()

  // --- WebSocket integration ---

  function handleWsMessage(data: unknown) {
    const msg = data as { event: string; task: TaskData }
    if (!msg?.event || !msg?.task) return

    if (msg.event === 'task_created') {
      // Add if not already present
      const exists = tasks.value.some((t) => t.id === msg.task.id)
      if (!exists) {
        tasks.value = [msg.task, ...tasks.value]
      }
    } else if (msg.event === 'task_updated') {
      tasks.value = tasks.value.map((t) =>
        t.id === msg.task.id ? msg.task : t
      )
    } else if (msg.event === 'task_deleted') {
      tasks.value = tasks.value.filter((t) => t.id !== msg.task.id)
    }
  }

  const { status: wsStatus, connect: wsConnect, disconnect: wsDisconnect } = useWebSocket({
    onMessage: handleWsMessage,
    getToken: () => auth.token,
  })

  // Watch WebSocket status for polling fallback
  watch(wsStatus, (newStatus: WebSocketStatus) => {
    if (newStatus === 'connected') {
      stopPolling()
    } else if (newStatus === 'disconnected') {
      startPolling()
    }
  })

  // --- Core data operations ---

  function tasksByStatus(status: TaskStatus): TaskData[] {
    return tasks.value.filter((t) => t.status === status)
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

  async function updateTask(id: string, data: { title?: string; description?: string; status?: TaskStatus; tags?: string[]; category?: string; execute_at?: string; repeat_interval?: string; repeat_until?: string }) {
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
    wsConnect()
  }

  function stop() {
    wsDisconnect()
    stopPolling()
  }

  return { tasks, loading, error, wsStatus, tasksByStatus, load, addTask, updateTask, removeTask, start, stop, startPolling, stopPolling }
})
