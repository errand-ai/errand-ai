<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { TaskData, TaskStatus } from '../composables/useApi'
import { fetchTags } from '../composables/useApi'

type Category = 'immediate' | 'scheduled' | 'repeating'

const props = defineProps<{
  task: TaskData
}>()

const emit = defineEmits<{
  save: [data: { title: string; description?: string; status: TaskStatus; tags: string[]; category?: string; execute_at?: string; repeat_interval?: string; repeat_until?: string }]
  cancel: []
  delete: []
}>()

const statuses: { key: TaskStatus; label: string }[] = [
  { key: 'new', label: 'New' },
  { key: 'scheduled', label: 'Scheduled' },
  { key: 'pending', label: 'Pending' },
  { key: 'running', label: 'Running' },
  { key: 'review', label: 'Review' },
  { key: 'completed', label: 'Completed' },
]

const categories: { key: Category; label: string }[] = [
  { key: 'immediate', label: 'Immediate' },
  { key: 'scheduled', label: 'Scheduled' },
  { key: 'repeating', label: 'Repeating' },
]

const quickIntervals = ['15m', '1h', '1d', '1w']

const title = ref(props.task.title)
const description = ref(props.task.description || '')
const status = ref<TaskStatus>(props.task.status)
const category = ref<Category>((props.task.category as Category) || 'immediate')
const executeAtLocal = ref(toLocalDatetime(props.task.execute_at))
const repeatInterval = ref(props.task.repeat_interval || '')
const repeatUntilLocal = ref(toLocalDatetime(props.task.repeat_until))
const tags = ref<string[]>([...(props.task.tags || [])])
const tagInput = ref('')
const tagSuggestions = ref<string[]>([])
const showSuggestions = ref(false)
const error = ref<string | null>(null)
const saving = ref(false)
const dialogRef = ref<HTMLDialogElement | null>(null)

const showRepeatFields = computed(() => category.value === 'repeating')
const isCompletedStatus = computed(() => ['review', 'completed'].includes(props.task.status))

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function toLocalDatetime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  // Format as YYYY-MM-DDTHH:mm for datetime-local input
  const offset = d.getTimezoneOffset()
  const local = new Date(d.getTime() - offset * 60000)
  return local.toISOString().slice(0, 16)
}

function toUtcIso(localDatetime: string): string | undefined {
  if (!localDatetime) return undefined
  return new Date(localDatetime).toISOString()
}

function formatDatetime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

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
    await emit('save', {
      title: title.value.trim(),
      description: description.value || undefined,
      status: status.value,
      tags: tags.value,
      category: category.value,
      execute_at: toUtcIso(executeAtLocal.value),
      repeat_interval: repeatInterval.value || undefined,
      repeat_until: toUtcIso(repeatUntilLocal.value),
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save'
  } finally {
    saving.value = false
  }
}

function onDeleteClick() {
  emit('delete')
}

function setQuickInterval(interval: string) {
  repeatInterval.value = interval
}

function onTagInputChange() {
  if (debounceTimer) clearTimeout(debounceTimer)
  const q = tagInput.value.trim()
  if (!q) {
    tagSuggestions.value = []
    showSuggestions.value = false
    return
  }
  debounceTimer = setTimeout(async () => {
    try {
      const results = await fetchTags(q)
      tagSuggestions.value = results
        .map((t) => t.name)
        .filter((name) => !tags.value.includes(name))
      showSuggestions.value = tagSuggestions.value.length > 0
    } catch {
      tagSuggestions.value = []
      showSuggestions.value = false
    }
  }, 200)
}

function addTag(name: string) {
  const trimmed = name.trim()
  if (trimmed && !tags.value.includes(trimmed)) {
    tags.value.push(trimmed)
  }
  tagInput.value = ''
  tagSuggestions.value = []
  showSuggestions.value = false
}

function removeTag(name: string) {
  tags.value = tags.value.filter((t) => t !== name)
}

function onTagKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    if (tagInput.value.trim()) {
      addTag(tagInput.value)
    }
  }
}

function onTagBlur() {
  setTimeout(() => { showSuggestions.value = false }, 150)
}
</script>

<template>
  <dialog
    ref="dialogRef"
    class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
    @cancel.prevent="onCancel"
  >
    <form method="dialog" class="w-[28rem] p-6" @submit.prevent="onSave">
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
        <label for="edit-description" class="mb-1 block text-sm font-medium text-gray-700">Description</label>
        <textarea
          id="edit-description"
          v-model="description"
          rows="3"
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

      <div class="mb-4">
        <label for="edit-category" class="mb-1 block text-sm font-medium text-gray-700">Category</label>
        <select
          id="edit-category"
          v-model="category"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          <option v-for="c in categories" :key="c.key" :value="c.key">{{ c.label }}</option>
        </select>
      </div>

      <div v-if="isCompletedStatus" class="mb-4">
        <label class="mb-1 block text-sm font-medium text-gray-700">Completed at</label>
        <p class="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600">
          {{ formatDatetime(task.updated_at) || 'Unknown' }}
        </p>
      </div>
      <div v-else class="mb-4">
        <label for="edit-execute-at" class="mb-1 block text-sm font-medium text-gray-700">Execute at</label>
        <input
          id="edit-execute-at"
          v-model="executeAtLocal"
          type="datetime-local"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      <div v-if="showRepeatFields" class="mb-4">
        <label for="edit-repeat-interval" class="mb-1 block text-sm font-medium text-gray-700">Repeat interval</label>
        <input
          id="edit-repeat-interval"
          v-model="repeatInterval"
          type="text"
          placeholder="e.g. 15m, 1h, 1d, 1w, or 0 9 * * MON-FRI"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <p class="mt-1 text-xs text-gray-500">
          Simple intervals (15m, 1h, 1d, 1w) or crontab (e.g. 0 9 * * MON-FRI)
        </p>
        <div class="mt-1.5 flex gap-1.5">
          <button
            v-for="qi in quickIntervals"
            :key="qi"
            type="button"
            class="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50"
            @click="setQuickInterval(qi)"
          >
            {{ qi }}
          </button>
        </div>
      </div>

      <div v-if="showRepeatFields" class="mb-4">
        <label for="edit-repeat-until" class="mb-1 block text-sm font-medium text-gray-700">Repeat until</label>
        <input
          id="edit-repeat-until"
          v-model="repeatUntilLocal"
          type="datetime-local"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      <div class="mb-4">
        <label class="mb-1 block text-sm font-medium text-gray-700">Tags</label>
        <div class="flex flex-wrap gap-1 mb-2" v-if="tags.length > 0">
          <span
            v-for="tag in tags"
            :key="tag"
            class="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700"
          >
            {{ tag }}
            <button
              type="button"
              class="text-blue-400 hover:text-blue-600"
              @click="removeTag(tag)"
            >
              &times;
            </button>
          </span>
        </div>
        <div class="relative">
          <input
            v-model="tagInput"
            type="text"
            placeholder="Add tag..."
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            @input="onTagInputChange"
            @keydown="onTagKeydown"
            @blur="onTagBlur"
          />
          <ul
            v-if="showSuggestions"
            class="absolute z-10 mt-1 w-full rounded-md border border-gray-200 bg-white shadow-lg max-h-40 overflow-y-auto"
          >
            <li
              v-for="suggestion in tagSuggestions"
              :key="suggestion"
              class="cursor-pointer px-3 py-2 text-sm hover:bg-blue-50"
              @mousedown.prevent="addTag(suggestion)"
            >
              {{ suggestion }}
            </li>
          </ul>
        </div>
      </div>

      <p v-if="error" class="mb-3 text-sm text-red-600">{{ error }}</p>

      <div class="flex items-center justify-between">
        <button
          type="button"
          class="rounded-md border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50"
          @click="onDeleteClick"
        >
          Delete
        </button>
        <div class="flex gap-2">
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
      </div>
    </form>
  </dialog>
</template>
