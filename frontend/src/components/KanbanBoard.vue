<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useTaskStore } from '../stores/tasks'
import { useAuthStore } from '../stores/auth'
import type { TaskStatus, TaskData } from '../composables/useApi'
import TaskCard from './TaskCard.vue'
import TaskForm from './TaskForm.vue'
import TaskEditModal from './TaskEditModal.vue'
import TaskOutputModal from './TaskOutputModal.vue'
import TaskLogModal from './TaskLogModal.vue'

const REORDERABLE_COLUMNS: TaskStatus[] = ['new', 'pending']

const store = useTaskStore()
const auth = useAuthStore()

const columns: { key: TaskStatus; label: string; color: string }[] = [
  { key: 'new', label: 'New', color: 'bg-sky-100' },
  { key: 'scheduled', label: 'Scheduled', color: 'bg-purple-100' },
  { key: 'pending', label: 'Pending', color: 'bg-yellow-100' },
  { key: 'running', label: 'Running', color: 'bg-blue-100' },
  { key: 'review', label: 'Review', color: 'bg-pink-100' },
  { key: 'completed', label: 'Completed', color: 'bg-green-100' },
]

const dragOverColumn = ref<TaskStatus | null>(null)
const editingTask = ref<TaskData | null>(null)
const dropIndicatorIndex = ref<number | null>(null)
const dropIndicatorColumn = ref<TaskStatus | null>(null)
const dragSourceStatus = ref<TaskStatus | null>(null)

// Delete confirmation modal state
const deleteConfirmTask = ref<TaskData | null>(null)
const deleteDialogRef = ref<HTMLDialogElement | null>(null)

// Output viewer modal state
const outputTask = ref<TaskData | null>(null)

// Log viewer modal state
const logTask = ref<TaskData | null>(null)

function onDragStart(e: DragEvent, task: TaskData) {
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', task.id)
  dragSourceStatus.value = task.status
}

function onDragOver(e: DragEvent, columnKey: TaskStatus) {
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'

  // Show drop indicator for intra-column reorder in reorderable columns
  if (
    dragSourceStatus.value === columnKey &&
    REORDERABLE_COLUMNS.includes(columnKey)
  ) {
    const columnEl = (e.currentTarget as HTMLElement).querySelector('[data-card-list]')
    if (columnEl) {
      const cards = Array.from(columnEl.children) as HTMLElement[]
      let insertIndex = cards.length
      for (let i = 0; i < cards.length; i++) {
        const rect = cards[i].getBoundingClientRect()
        if (e.clientY < rect.top + rect.height / 2) {
          insertIndex = i
          break
        }
      }
      dropIndicatorIndex.value = insertIndex
      dropIndicatorColumn.value = columnKey
    }
  } else {
    dropIndicatorIndex.value = null
    dropIndicatorColumn.value = null
  }
}

function onDragEnter(columnKey: TaskStatus) {
  dragOverColumn.value = columnKey
}

function onDragLeave(e: DragEvent, columnKey: TaskStatus) {
  const related = e.relatedTarget as HTMLElement | null
  const currentTarget = e.currentTarget as HTMLElement
  if (!related || !currentTarget.contains(related)) {
    if (dragOverColumn.value === columnKey) {
      dragOverColumn.value = null
    }
    if (dropIndicatorColumn.value === columnKey) {
      dropIndicatorIndex.value = null
      dropIndicatorColumn.value = null
    }
  }
}

async function onDrop(e: DragEvent, targetStatus: TaskStatus) {
  e.preventDefault()
  dragOverColumn.value = null
  dropIndicatorIndex.value = null
  dropIndicatorColumn.value = null

  const taskId = e.dataTransfer!.getData('text/plain')
  const task = store.tasks.find((t) => t.id === taskId)
  if (!task) return

  if (task.status === targetStatus) {
    // Intra-column reorder (only for reorderable columns)
    if (!REORDERABLE_COLUMNS.includes(targetStatus)) return

    const columnEl = (e.currentTarget as HTMLElement).querySelector('[data-card-list]')
    if (!columnEl) return

    const cards = Array.from(columnEl.children) as HTMLElement[]
    const columnTasks = store.tasksByStatus(targetStatus)
    let insertIndex = cards.length
    for (let i = 0; i < cards.length; i++) {
      const rect = cards[i].getBoundingClientRect()
      if (e.clientY < rect.top + rect.height / 2) {
        insertIndex = i
        break
      }
    }

    // Calculate the target position value
    const targetPosition = insertIndex < columnTasks.length
      ? columnTasks[insertIndex].position
      : (columnTasks.length > 0 ? columnTasks[columnTasks.length - 1].position + 1 : 1)

    if (targetPosition === task.position) return

    try {
      await store.updateTask(taskId, { position: targetPosition })
    } catch {
      // Error is set in store; reverts on next refresh
    }
    return
  }

  // Cross-column move
  try {
    await store.updateTask(taskId, { status: targetStatus })
  } catch {
    // Error is set in store; card reverts on next poll
  }
}

function onDragEnd() {
  dragSourceStatus.value = null
  dropIndicatorIndex.value = null
  dropIndicatorColumn.value = null
}

function onEdit(task: TaskData) {
  editingTask.value = { ...task }
}

async function onSave(data: { title: string; description?: string; status: TaskStatus; tags?: string[]; category?: string; execute_at?: string; repeat_interval?: string; repeat_until?: string }) {
  if (!editingTask.value) return
  try {
    await store.updateTask(editingTask.value.id, data)
    editingTask.value = null
  } catch {
    // Error shown by modal via rejection
    throw new Error(store.error || 'Failed to save')
  }
}

function showDeleteConfirm(task: TaskData) {
  deleteConfirmTask.value = task
  // Use nextTick-like approach: showModal after DOM update
  setTimeout(() => deleteDialogRef.value?.showModal(), 0)
}

async function confirmDelete() {
  if (!deleteConfirmTask.value) return
  const taskId = deleteConfirmTask.value.id
  deleteDialogRef.value?.close()
  deleteConfirmTask.value = null
  // Close edit modal if open
  editingTask.value = null
  try {
    await store.removeTask(taskId)
  } catch {
    // Error is set in store
  }
}

function cancelDelete() {
  deleteDialogRef.value?.close()
  deleteConfirmTask.value = null
}

function onDeleteDialogClick(e: MouseEvent) {
  // Close on backdrop click
  const dialog = deleteDialogRef.value
  if (dialog && e.target === dialog) {
    cancelDelete()
  }
}

function onDelete(task: TaskData) {
  showDeleteConfirm(task)
}

function onModalDelete() {
  if (!editingTask.value) return
  showDeleteConfirm(editingTask.value)
}

function onViewOutput(task: TaskData) {
  outputTask.value = task
}

function onViewLogs(task: TaskData) {
  logTask.value = task
}

function onCancel() {
  editingTask.value = null
}

onMounted(() => store.start())
onUnmounted(() => store.stop())
</script>

<template>
  <div v-if="!auth.isViewer" class="mb-6 mx-auto max-w-7xl">
    <TaskForm />
  </div>
  <p v-if="store.error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ store.error }}</p>

  <!-- Skeleton loading state -->
  <div v-if="store.loading && store.tasks.length === 0" class="flex gap-4 overflow-x-auto pb-4" data-testid="skeleton-loading">
    <div v-for="i in 6" :key="i" class="min-w-[240px] flex-1 rounded-lg bg-gray-100 p-4">
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

  <div v-else class="flex gap-4 overflow-x-auto pb-4" style="min-width: 0;">
    <div
      v-for="col in columns"
      :key="col.key"
      :class="[col.color, 'rounded-lg p-4 min-w-[240px] flex-1', !auth.isViewer && dragOverColumn === col.key ? 'ring-2 ring-blue-400 ring-inset' : '']"
      @dragover="onDragOver($event, col.key)"
      @dragenter="onDragEnter(col.key)"
      @dragleave="onDragLeave($event, col.key)"
      @drop="onDrop($event, col.key)"
    >
      <h2 class="mb-3 flex items-center gap-2 text-sm font-semibold uppercase text-gray-700">
        {{ col.label }}
        <span class="inline-flex items-center justify-center rounded-full bg-white/70 px-1.5 text-xs font-medium text-gray-600" data-testid="column-count">{{ store.tasksByStatus(col.key).length }}</span>
      </h2>
      <div data-card-list class="flex flex-col gap-2">
        <template v-for="(task, index) in store.tasksByStatus(col.key)" :key="task.id">
          <div
            v-if="dropIndicatorColumn === col.key && dropIndicatorIndex === index"
            class="h-1 rounded bg-blue-400"
          />
          <TaskCard
            :task="task"
            :column-status="col.key"
            :hide-delete="auth.isViewer || col.key === 'running'"
            :disable-drag="auth.isViewer"
            @dragstart="onDragStart($event, task)"
            @dragend="onDragEnd"
            @edit="onEdit(task)"
            @delete="onDelete(task)"
            @view-output="onViewOutput(task)"
            @view-logs="onViewLogs(task)"
          />
        </template>
        <div
          v-if="dropIndicatorColumn === col.key && dropIndicatorIndex === store.tasksByStatus(col.key).length"
          class="h-1 rounded bg-blue-400"
        />
      </div>
    </div>
  </div>
  <TaskEditModal
    v-if="editingTask"
    :task="editingTask"
    :read-only="auth.isViewer || editingTask.status === 'running'"
    @save="onSave"
    @cancel="onCancel"
    @delete="onModalDelete"
  />

  <TaskOutputModal
    v-if="outputTask"
    :title="outputTask.title"
    :output="outputTask.output ?? null"
    @close="outputTask = null"
  />

  <TaskLogModal
    v-if="logTask"
    :task-id="logTask.id"
    :title="logTask.title"
    @close="logTask = null"
  />

  <!-- Delete confirmation modal -->
  <dialog
    ref="deleteDialogRef"
    class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
    @cancel.prevent="cancelDelete"
    @click="onDeleteDialogClick"
  >
    <div class="w-80 p-6">
      <h3 class="mb-2 text-lg font-semibold text-gray-800">Delete this task?</h3>
      <p v-if="deleteConfirmTask" class="mb-4 text-sm text-gray-600">{{ deleteConfirmTask.title }}</p>
      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          @click="cancelDelete"
        >
          Cancel
        </button>
        <button
          type="button"
          class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
          @click="confirmDelete"
        >
          Delete
        </button>
      </div>
    </div>
  </dialog>
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
