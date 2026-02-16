<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { fetchArchivedTasks } from '../composables/useApi'
import type { TaskData } from '../composables/useApi'
import TaskEditModal from '../components/TaskEditModal.vue'
import TaskOutputModal from '../components/TaskOutputModal.vue'

const tasks = ref<TaskData[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedTask = ref<TaskData | null>(null)
const outputTask = ref<TaskData | null>(null)

const searchQuery = ref('')
const statusFilter = ref('all')
const sortColumn = ref<'title' | 'status' | 'date'>('date')
const sortDirection = ref<'asc' | 'desc'>('desc')

const filteredTasks = computed(() => {
  let result = [...tasks.value]

  // Search filter
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(t => t.title.toLowerCase().includes(q))
  }

  // Status filter
  if (statusFilter.value !== 'all') {
    result = result.filter(t => t.status === statusFilter.value)
  }

  // Sort
  result.sort((a, b) => {
    let cmp = 0
    if (sortColumn.value === 'title') {
      cmp = a.title.localeCompare(b.title)
    } else if (sortColumn.value === 'status') {
      cmp = a.status.localeCompare(b.status)
    } else {
      cmp = (a.updated_at || '').localeCompare(b.updated_at || '')
    }
    return sortDirection.value === 'asc' ? cmp : -cmp
  })

  return result
})

function toggleSort(column: 'title' | 'status' | 'date') {
  if (sortColumn.value === column) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = column
    sortDirection.value = 'asc'
  }
}

function sortIndicator(column: string): string {
  if (sortColumn.value !== column) return ''
  return sortDirection.value === 'asc' ? ' \u2191' : ' \u2193'
}

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

    <!-- Skeleton loading state -->
    <div v-if="loading" data-testid="skeleton-loading">
      <div class="mb-4 flex gap-3">
        <div class="h-9 w-64 animate-pulse rounded-md bg-gray-200"></div>
        <div class="h-9 w-32 animate-pulse rounded-md bg-gray-200"></div>
      </div>
      <div class="space-y-2">
        <div v-for="i in 5" :key="i" class="h-12 animate-pulse rounded bg-gray-200"></div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="tasks.length === 0"
      class="flex flex-col items-center justify-center py-16 text-gray-400"
      data-testid="archive-empty-state"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="mb-3 h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
      </svg>
      <p class="text-lg font-medium">No archived tasks yet</p>
      <p class="text-sm">Completed tasks are automatically archived after the configured retention period</p>
    </div>

    <template v-else>
      <!-- Search, filter, and count -->
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search tasks..."
          class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          data-testid="search-input"
        />
        <select
          v-model="statusFilter"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          data-testid="status-filter"
        >
          <option value="all">All</option>
          <option value="archived">Archived</option>
          <option value="deleted">Deleted</option>
        </select>
        <span class="text-sm text-gray-500" data-testid="result-count">{{ filteredTasks.length }} tasks</span>
      </div>

      <table class="w-full text-left text-sm">
        <thead>
          <tr class="border-b border-gray-200">
            <th
              class="cursor-pointer py-3 pr-4 font-medium text-gray-700 hover:text-gray-900"
              @click="toggleSort('title')"
              data-testid="sort-title"
            >
              Title{{ sortIndicator('title') }}
            </th>
            <th
              class="cursor-pointer py-3 pr-4 font-medium text-gray-700 hover:text-gray-900"
              @click="toggleSort('status')"
              data-testid="sort-status"
            >
              Status{{ sortIndicator('status') }}
            </th>
            <th class="py-3 pr-4 font-medium text-gray-700">Tags</th>
            <th
              class="cursor-pointer py-3 pr-4 font-medium text-gray-700 hover:text-gray-900"
              @click="toggleSort('date')"
              data-testid="sort-date"
            >
              Date{{ sortIndicator('date') }}
            </th>
            <th class="py-3 font-medium text-gray-700">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="task in filteredTasks"
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
    </template>

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
