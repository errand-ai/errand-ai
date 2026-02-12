<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchArchivedTasks } from '../composables/useApi'
import type { TaskData } from '../composables/useApi'
import TaskEditModal from '../components/TaskEditModal.vue'
import TaskOutputModal from '../components/TaskOutputModal.vue'

const tasks = ref<TaskData[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedTask = ref<TaskData | null>(null)
const outputTask = ref<TaskData | null>(null)

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function statusBadgeClass(status: string): string {
  if (status === 'archived') return 'bg-gray-100 text-gray-700'
  if (status === 'deleted') return 'bg-red-100 text-red-700'
  return 'bg-blue-100 text-blue-700'
}

function onRowClick(task: TaskData) {
  selectedTask.value = { ...task }
}

function onModalCancel() {
  selectedTask.value = null
}

onMounted(async () => {
  try {
    tasks.value = await fetchArchivedTasks()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load archived tasks'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <h2 class="text-2xl font-bold text-gray-900 mb-6">Archived Tasks</h2>

    <div v-if="error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</div>
    <div v-if="loading" class="text-sm text-gray-500">Loading archived tasks...</div>

    <div v-else-if="tasks.length === 0" class="text-sm text-gray-500 italic">No archived tasks.</div>

    <table v-else class="w-full text-left text-sm">
      <thead>
        <tr class="border-b border-gray-200">
          <th class="py-3 pr-4 font-medium text-gray-700">Title</th>
          <th class="py-3 pr-4 font-medium text-gray-700">Status</th>
          <th class="py-3 pr-4 font-medium text-gray-700">Tags</th>
          <th class="py-3 pr-4 font-medium text-gray-700">Date</th>
          <th class="py-3 font-medium text-gray-700">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="task in tasks"
          :key="task.id"
          class="border-b border-gray-100 cursor-pointer hover:bg-gray-50"
          @click="onRowClick(task)"
        >
          <td class="py-3 pr-4 text-gray-800">{{ task.title }}</td>
          <td class="py-3 pr-4">
            <span :class="[statusBadgeClass(task.status), 'inline-block rounded-full px-2 py-0.5 text-xs font-medium']">
              {{ task.status }}
            </span>
          </td>
          <td class="py-3 pr-4">
            <div class="flex flex-wrap gap-1">
              <span
                v-for="tag in task.tags"
                :key="tag"
                class="inline-block rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700"
              >
                {{ tag }}
              </span>
            </div>
          </td>
          <td class="py-3 pr-4 text-gray-600">{{ formatDate(task.updated_at) }}</td>
          <td class="py-3">
            <button
              v-if="task.output"
              type="button"
              class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
              @click.stop="outputTask = task"
            >
              View Output
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <TaskEditModal
      v-if="selectedTask"
      :task="selectedTask"
      :read-only="true"
      @cancel="onModalCancel"
      @save="() => {}"
      @delete="() => {}"
    />

    <TaskOutputModal
      v-if="outputTask"
      :title="outputTask.title"
      :output="outputTask.output ?? null"
      @close="outputTask = null"
    />
  </div>
</template>
