import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { fetchTasks, createTask, type TaskData } from '../composables/useApi'

const POLL_INTERVAL = 5000

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<TaskData[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  const pending = computed(() => tasks.value.filter((t) => t.status === 'pending'))
  const running = computed(() => tasks.value.filter((t) => t.status === 'running'))
  const completed = computed(() => tasks.value.filter((t) => t.status === 'completed'))
  const failed = computed(() => tasks.value.filter((t) => t.status === 'failed'))

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

  async function addTask(title: string) {
    try {
      await createTask(title)
      error.value = null
      await load()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create task'
      throw e
    }
  }

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

  return { tasks, loading, error, pending, running, completed, failed, load, addTask, startPolling, stopPolling }
})
