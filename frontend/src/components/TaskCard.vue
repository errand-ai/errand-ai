<script setup lang="ts">
import type { TaskStatus } from '../composables/useApi'

defineProps<{
  title: string
  status: TaskStatus
}>()
</script>

<template>
  <div class="rounded-lg bg-white p-3 shadow">
    <p class="text-sm text-gray-800">{{ title }}</p>
    <p class="mt-1 text-xs text-gray-500 capitalize">{{ status }}</p>
  </div>
</template>
