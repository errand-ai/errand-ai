import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchTasks, createTask, updateTask as apiUpdateTask, type TaskData, type TaskStatus } from '../composables/useApi'

const POLL_INTERVAL = 5000

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<TaskData[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | null = null

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

  async function updateTask(id: string, data: { title?: string; status?: TaskStatus }) {
    try {
      await apiUpdateTask(id, data)
      error.value = null
      await load()
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update task'
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

  return { tasks, loading, error, tasksByStatus, load, addTask, updateTask, startPolling, stopPolling }
})
