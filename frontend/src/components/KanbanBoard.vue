<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useTaskStore } from '../stores/tasks'
import type { TaskStatus, TaskData } from '../composables/useApi'
import TaskCard from './TaskCard.vue'
import TaskForm from './TaskForm.vue'
import TaskEditModal from './TaskEditModal.vue'

const store = useTaskStore()

const columns: { key: TaskStatus; label: string; color: string }[] = [
  { key: 'new', label: 'New', color: 'bg-sky-100' },
  { key: 'need-input', label: 'Need Input', color: 'bg-orange-100' },
  { key: 'scheduled', label: 'Scheduled', color: 'bg-purple-100' },
  { key: 'pending', label: 'Pending', color: 'bg-yellow-100' },
  { key: 'running', label: 'Running', color: 'bg-blue-100' },
  { key: 'review', label: 'Review', color: 'bg-pink-100' },
  { key: 'completed', label: 'Completed', color: 'bg-green-100' },
]

const dragOverColumn = ref<TaskStatus | null>(null)
const editingTask = ref<TaskData | null>(null)

function onDragStart(e: DragEvent, taskId: string) {
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', taskId)
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'
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
  }
}

async function onDrop(e: DragEvent, targetStatus: TaskStatus) {
  e.preventDefault()
  dragOverColumn.value = null
  const taskId = e.dataTransfer!.getData('text/plain')
  const task = store.tasks.find((t) => t.id === taskId)
  if (!task || task.status === targetStatus) return
  try {
    await store.updateTask(taskId, { status: targetStatus })
  } catch {
    // Error is set in store; card reverts on next poll
  }
}

function onEdit(task: TaskData) {
  editingTask.value = { ...task }
}

async function onSave(data: { title: string; status: TaskStatus }) {
  if (!editingTask.value) return
  try {
    await store.updateTask(editingTask.value.id, data)
    editingTask.value = null
  } catch {
    // Error shown by modal via rejection
    throw new Error(store.error || 'Failed to save')
  }
}

function onCancel() {
  editingTask.value = null
}

onMounted(() => store.startPolling())
onUnmounted(() => store.stopPolling())
</script>

<template>
  <div class="mb-6 mx-auto max-w-7xl">
    <TaskForm />
  </div>
  <p v-if="store.error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ store.error }}</p>
  <p v-if="store.loading && store.tasks.length === 0" class="mb-4 text-sm text-gray-500">Loading tasks...</p>
  <div class="flex gap-4 overflow-x-auto pb-4" style="min-width: 0;">
    <div
      v-for="col in columns"
      :key="col.key"
      :class="[col.color, 'rounded-lg p-4 min-w-[100px] flex-1', dragOverColumn === col.key ? 'ring-2 ring-blue-400 ring-inset' : '']"
      @dragover="onDragOver"
      @dragenter="onDragEnter(col.key)"
      @dragleave="onDragLeave($event, col.key)"
      @drop="onDrop($event, col.key)"
    >
      <h2 class="mb-3 text-sm font-semibold uppercase text-gray-700">
        {{ col.label }}
        <span class="ml-1 text-gray-500">({{ store.tasksByStatus(col.key).length }})</span>
      </h2>
      <TransitionGroup name="task" tag="div" class="flex flex-col gap-2">
        <TaskCard
          v-for="task in store.tasksByStatus(col.key)"
          :key="task.id"
          :task="task"
          @dragstart="onDragStart($event, task.id)"
          @edit="onEdit(task)"
        />
      </TransitionGroup>
      <p v-if="store.tasksByStatus(col.key).length === 0" class="text-xs text-gray-400 italic">
        No tasks
      </p>
    </div>
  </div>
  <TaskEditModal
    v-if="editingTask"
    :task="editingTask"
    @save="onSave"
    @cancel="onCancel"
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
