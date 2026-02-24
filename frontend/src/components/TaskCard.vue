<script setup lang="ts">
import { computed } from 'vue'
import type { TaskData } from '../composables/useApi'
import { formatRelativeTime } from '../composables/useRelativeTime'
import { useNow } from '../composables/useNow'

const props = defineProps<{
  task: TaskData
  columnStatus?: string
  hideDelete?: boolean
  disableDrag?: boolean
}>()

defineEmits<{
  edit: []
  delete: []
  'view-output': []
  'view-logs': []
}>()

const hasExecuteAt = computed(() => !!props.task.execute_at)
const isRunning = computed(() => props.columnStatus === 'running')
const isRepeating = computed(() => props.task.category === 'repeating')

const now = useNow(30000, hasExecuteAt)

const relativeTime = computed(() => {
  if (!props.task.execute_at) return ''
  return formatRelativeTime(props.task.execute_at, now.value)
})

const showLogButton = computed(() => {
  const col = props.columnStatus
  return col === 'running'
    || ((col === 'review' || col === 'completed' || col === 'scheduled') && props.task.runner_logs != null)
})

const showOutputButton = computed(() => {
  const col = props.columnStatus
  return (col === 'review' || col === 'completed' || col === 'scheduled') && !!props.task.output
})
</script>

<template>
  <div
    class="rounded-lg bg-white p-3 shadow"
    :class="[
      disableDrag ? 'cursor-default' : 'cursor-grab active:cursor-grabbing',
      isRunning ? 'border-l-2 border-blue-400' : '',
    ]"
    :draggable="!disableDrag"
  >
    <div class="flex items-start justify-between gap-2">
      <p class="text-sm text-gray-800">{{ task.title }}</p>
      <div class="flex shrink-0 gap-0.5">
        <button
          v-if="showLogButton"
          class="rounded p-1 text-gray-400 hover:bg-blue-50 hover:text-blue-600"
          title="View logs"
          @click.stop="$emit('view-logs')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd" />
          </svg>
        </button>
        <button
          v-if="showOutputButton"
          class="rounded p-1 text-gray-400 hover:bg-blue-50 hover:text-blue-600"
          title="View output"
          @click.stop="$emit('view-output')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
            <path fill-rule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clip-rule="evenodd" />
          </svg>
        </button>
        <button
          class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          title="Edit task"
          @click.stop="$emit('edit')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
          </svg>
        </button>
        <button
          v-if="!hideDelete"
          class="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
          title="Delete task"
          @click.stop="$emit('delete')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
    </div>
    <p
      v-if="task.description"
      class="mt-0.5 text-xs text-gray-500 line-clamp-2"
      data-testid="description-preview"
    >
      {{ task.description }}
    </p>
    <div v-if="isRunning" class="mt-1 flex items-center gap-1.5" data-testid="running-indicator">
      <span class="relative flex h-2.5 w-2.5">
        <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75"></span>
        <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-blue-500"></span>
      </span>
      <span class="text-xs text-blue-600">Running...</span>
    </div>
    <div v-if="isRepeating && task.repeat_interval" class="mt-1 flex items-center gap-1" data-testid="repeating-indicator">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
        <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
      </svg>
      <span class="text-xs text-gray-500">{{ task.repeat_interval }}</span>
    </div>
    <p
      v-if="task.execute_at"
      class="mt-1 text-xs text-blue-600"
      data-testid="execute-at-time"
    >
      {{ relativeTime }}
    </p>
    <div v-if="task.tags && task.tags.length > 0" class="mt-1.5 flex flex-wrap gap-1">
      <span
        v-for="tag in task.tags"
        :key="tag"
        class="inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
      >
        {{ tag }}
      </span>
    </div>
  </div>
</template>
