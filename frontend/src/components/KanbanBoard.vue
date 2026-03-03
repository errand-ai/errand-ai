<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useTaskStore } from '../stores/tasks'
import { useAuthStore } from '../stores/auth'
import {
  TaskBoard,
  TaskForm,
  TaskEditModal,
  TaskOutputModal,
  TaskLogViewer,
  DeleteConfirmModal,
  AudioRecorder,
} from '@errand-ai/ui-components'
import type { TaskData, TaskStatus } from '@errand-ai/ui-components'

const store = useTaskStore()
const auth = useAuthStore()

const editingTask = ref<TaskData | null>(null)
const outputTask = ref<TaskData | null>(null)
const logTask = ref<TaskData | null>(null)
const deleteConfirmTask = ref<TaskData | null>(null)

const userRole = (() => {
  if (auth.isAdmin) return 'admin'
  if (auth.isEditor) return 'editor'
  return 'viewer'
})()

function onTaskUpdate(payload: { id: string; status?: TaskStatus; position?: number }) {
  store.updateTask(payload.id, payload)
}

function onTaskCreated() {
  store.load()
}

function onEdit(task: TaskData) {
  editingTask.value = { ...task }
}

async function onSave(data: { title: string; description?: string; status: TaskStatus; tags: string[]; category?: string; execute_at?: string; repeat_interval?: string; repeat_until?: string; profile_id?: string | null }) {
  if (!editingTask.value) return
  try {
    await store.updateTask(editingTask.value.id, data)
    editingTask.value = null
  } catch {
    throw new Error(store.error || 'Failed to save')
  }
}

function onDelete(task: TaskData) {
  deleteConfirmTask.value = task
}

function onModalDelete() {
  if (!editingTask.value) return
  deleteConfirmTask.value = editingTask.value
}

async function confirmDelete() {
  if (!deleteConfirmTask.value) return
  const taskId = deleteConfirmTask.value.id
  deleteConfirmTask.value = null
  editingTask.value = null
  try {
    await store.removeTask(taskId)
  } catch {
    // Error is set in store
  }
}

function onViewOutput(task: TaskData) {
  outputTask.value = task
}

function onViewLiveLogs(task: TaskData) {
  logTask.value = task
}

function onViewStaticLogs(task: TaskData) {
  logTask.value = task
}

function logStreamUrl(): string {
  const token = auth.token ?? ''
  return `/api/tasks/{taskId}/logs/stream?token=${encodeURIComponent(token)}`
}

onMounted(() => store.start())
onUnmounted(() => store.stop())
</script>

<template>
  <div v-if="!auth.isViewer" class="mb-6 mx-auto max-w-7xl">
    <TaskForm @task-created="onTaskCreated">
      <template #voice="{ onTranscription }">
        <AudioRecorder @transcription="onTranscription" />
      </template>
    </TaskForm>
  </div>
  <p v-if="store.error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ store.error }}</p>

  <!-- Skeleton loading state -->
  <div v-if="store.loading && store.tasks.length === 0" class="flex gap-4 overflow-x-auto pb-4" data-testid="skeleton-loading">
    <div v-for="i in 5" :key="i" class="min-w-[240px] flex-1 rounded-lg bg-gray-100 p-4">
      <div class="mb-3 h-4 w-24 animate-pulse rounded bg-gray-300"></div>
      <div class="space-y-2">
        <div class="h-16 animate-pulse rounded-lg bg-gray-200"></div>
        <div class="h-16 animate-pulse rounded-lg bg-gray-200"></div>
      </div>
    </div>
  </div>

  <!-- Board-level empty state -->
  <div
    v-else-if="!store.loading && store.tasks.length === 0"
    class="flex flex-col items-center justify-center py-16 text-gray-400"
    data-testid="board-empty-state"
  >
    <svg xmlns="http://www.w3.org/2000/svg" class="mb-3 h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
    </svg>
    <p class="text-lg font-medium">No tasks yet</p>
    <p class="text-sm">Create your first task using the form above</p>
  </div>

  <TaskBoard
    v-else
    :tasks="store.tasks"
    :user-role="userRole"
    :loading="store.loading"
    @task-update="onTaskUpdate"
    @task-edit="onEdit"
    @task-delete="onDelete"
    @view-output="onViewOutput"
    @view-live-logs="onViewLiveLogs"
    @view-static-logs="onViewStaticLogs"
  />

  <TaskEditModal
    v-if="editingTask"
    :task="editingTask"
    :read-only="auth.isViewer || editingTask.status === 'running' || editingTask.status === 'completed'"
    @save="onSave"
    @cancel="editingTask = null"
    @delete="onModalDelete"
  />

  <TaskOutputModal
    v-if="outputTask"
    :title="outputTask.title"
    :output="outputTask.output ?? null"
    @close="outputTask = null"
  />

  <Teleport to="body">
    <div v-if="logTask" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="logTask = null">
      <div class="w-full max-w-4xl m-4" style="height: 70vh;">
        <TaskLogViewer
          :mode="logTask.status === 'running' ? 'live' : 'static'"
          :task-id="logTask.status === 'running' ? logTask.id : undefined"
          :log-data="logTask.status !== 'running' ? (logTask.runner_logs ?? undefined) : undefined"
          :stream-url="logStreamUrl()"
          @close="logTask = null"
          @finished="() => {}"
        />
      </div>
    </div>
  </Teleport>

  <DeleteConfirmModal
    v-if="deleteConfirmTask"
    :title="deleteConfirmTask.title"
    @confirm="confirmDelete"
    @cancel="deleteConfirmTask = null"
  />
</template>

<style scoped>
.task-enter-active,
.task-leave-active {
  transition: all 0.3s ease;
}
.task-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}
.task-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
.task-move {
  transition: transform 0.3s ease;
}
</style>
