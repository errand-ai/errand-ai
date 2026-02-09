<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { TaskData, TaskStatus } from '../composables/useApi'

const props = defineProps<{
  task: TaskData
}>()

const emit = defineEmits<{
  save: [data: { title: string; status: TaskStatus }]
  cancel: []
}>()

const statuses: { key: TaskStatus; label: string }[] = [
  { key: 'new', label: 'New' },
  { key: 'need-input', label: 'Need Input' },
  { key: 'scheduled', label: 'Scheduled' },
  { key: 'pending', label: 'Pending' },
  { key: 'running', label: 'Running' },
  { key: 'review', label: 'Review' },
  { key: 'completed', label: 'Completed' },
]

const title = ref(props.task.title)
const status = ref<TaskStatus>(props.task.status)
const error = ref<string | null>(null)
const saving = ref(false)
const dialogRef = ref<HTMLDialogElement | null>(null)

onMounted(() => {
  dialogRef.value?.showModal()
})

function onCancel() {
  dialogRef.value?.close()
  emit('cancel')
}

async function onSave() {
  if (!title.value.trim()) {
    error.value = 'Title cannot be empty'
    return
  }
  error.value = null
  saving.value = true
  try {
    await emit('save', { title: title.value.trim(), status: status.value })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <dialog
    ref="dialogRef"
    class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
    @cancel.prevent="onCancel"
  >
    <form method="dialog" class="w-96 p-6" @submit.prevent="onSave">
      <h3 class="mb-4 text-lg font-semibold text-gray-800">Edit Task</h3>

      <div class="mb-4">
        <label for="edit-title" class="mb-1 block text-sm font-medium text-gray-700">Title</label>
        <input
          id="edit-title"
          v-model="title"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      <div class="mb-4">
        <label for="edit-status" class="mb-1 block text-sm font-medium text-gray-700">Status</label>
        <select
          id="edit-status"
          v-model="status"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option v-for="s in statuses" :key="s.key" :value="s.key">{{ s.label }}</option>
        </select>
      </div>

      <p v-if="error" class="mb-3 text-sm text-red-600">{{ error }}</p>

      <div class="flex justify-end gap-2">
        <button
          type="button"
          class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          @click="onCancel"
        >
          Cancel
        </button>
        <button
          type="submit"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          :disabled="saving"
        >
          {{ saving ? 'Saving...' : 'Save' }}
        </button>
      </div>
    </form>
  </dialog>
</template>
