<script setup lang="ts">
import { computed } from 'vue'
import type { TaskData } from '../composables/useApi'
import { formatRelativeTime } from '../composables/useRelativeTime'

const props = defineProps<{
  task: TaskData
  columnStatus?: string
}>()

defineEmits<{
  edit: []
  delete: []
  'view-output': []
}>()

const showOutputButton = computed(() => {
  const col = props.columnStatus
  return (col === 'review' || col === 'completed' || col === 'scheduled') && !!props.task.output
})
</script>

<template>
  <div class="rounded-lg bg-white p-3 shadow cursor-grab active:cursor-grabbing" draggable="true">
    <div class="flex items-start justify-between gap-2">
      <p class="text-sm text-gray-800">{{ task.title }}</p>
      <div class="flex shrink-0 gap-0.5">
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
      v-if="columnStatus === 'scheduled' && task.execute_at"
      class="mt-1 text-xs text-blue-600"
    >
      {{ formatRelativeTime(task.execute_at) }}
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
