<script setup lang="ts">
import { ref } from 'vue'
import { useTaskStore } from '../stores/tasks'

const store = useTaskStore()
const title = ref('')
const error = ref('')

async function submit() {
  const trimmed = title.value.trim()
  if (!trimmed) {
    error.value = 'Title cannot be empty'
    return
  }
  error.value = ''
  try {
    await store.addTask(trimmed)
    title.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create task'
  }
}
</script>

<template>
  <form @submit.prevent="submit" class="flex gap-2">
    <input
      v-model="title"
      type="text"
      placeholder="New task title..."
      class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
    />
    <button
      type="submit"
      class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
    >
      Add Task
    </button>
  </form>
  <p v-if="error" class="mt-1 text-sm text-red-600">{{ error }}</p>
</template>
