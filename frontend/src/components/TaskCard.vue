<script setup lang="ts">
import type { TaskData } from '../composables/useApi'

defineProps<{
  task: TaskData
}>()

defineEmits<{
  edit: []
}>()
</script>

<template>
  <div class="rounded-lg bg-white p-3 shadow cursor-grab active:cursor-grabbing" draggable="true">
    <div class="flex items-start justify-between gap-2">
      <p class="text-sm text-gray-800">{{ task.title }}</p>
      <button
        class="shrink-0 rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        title="Edit task"
        @click.stop="$emit('edit')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
          <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
        </svg>
      </button>
    </div>
    <p class="mt-1 text-xs text-gray-500 capitalize">{{ task.status }}</p>
  </div>
</template>
