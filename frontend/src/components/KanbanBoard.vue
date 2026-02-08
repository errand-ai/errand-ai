<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useTaskStore } from '../stores/tasks'
import TaskCard from './TaskCard.vue'
import TaskForm from './TaskForm.vue'

const store = useTaskStore()

const columns = [
  { key: 'pending', label: 'Pending', color: 'bg-yellow-100' },
  { key: 'running', label: 'Running', color: 'bg-blue-100' },
  { key: 'completed', label: 'Completed', color: 'bg-green-100' },
  { key: 'failed', label: 'Failed', color: 'bg-red-100' },
] as const

function tasksForColumn(key: string) {
  switch (key) {
    case 'pending': return store.pending
    case 'running': return store.running
    case 'completed': return store.completed
    case 'failed': return store.failed
    default: return []
  }
}

onMounted(() => store.startPolling())
onUnmounted(() => store.stopPolling())
</script>

<template>
  <div class="mb-6">
    <TaskForm />
  </div>
  <p v-if="store.error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ store.error }}</p>
  <p v-if="store.loading && store.tasks.length === 0" class="mb-4 text-sm text-gray-500">Loading tasks...</p>
  <div class="grid grid-cols-4 gap-4">
    <div v-for="col in columns" :key="col.key" :class="[col.color, 'rounded-lg p-4']">
      <h2 class="mb-3 text-sm font-semibold uppercase text-gray-700">
        {{ col.label }}
        <span class="ml-1 text-gray-500">({{ tasksForColumn(col.key).length }})</span>
      </h2>
      <TransitionGroup name="task" tag="div" class="flex flex-col gap-2">
        <TaskCard v-for="task in tasksForColumn(col.key)" :key="task.id" :title="task.title" :status="task.status" />
      </TransitionGroup>
      <p v-if="tasksForColumn(col.key).length === 0" class="text-xs text-gray-400 italic">
        No tasks
      </p>
    </div>
  </div>
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
