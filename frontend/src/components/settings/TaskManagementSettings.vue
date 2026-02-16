<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'

const props = defineProps<{
  timezone: string
  archiveAfterDays: number
  taskRunnerLogLevel: string
  saveSettings: (data: Record<string, unknown>) => Promise<void>
}>()

const emit = defineEmits<{
  'update:timezone': [value: string]
  'update:archiveAfterDays': [value: number]
  'update:taskRunnerLogLevel': [value: string]
}>()

const localTimezone = ref(props.timezone)
const localArchiveDays = ref(props.archiveAfterDays)
const localLogLevel = ref(props.taskRunnerLogLevel)
const timezones = ref<string[]>([])
const saving = ref(false)

const isDirty = computed(() =>
  localTimezone.value !== props.timezone
  || localArchiveDays.value !== props.archiveAfterDays
  || localLogLevel.value !== props.taskRunnerLogLevel
)

onMounted(() => {
  try {
    const zones = Intl.supportedValuesOf('timeZone')
    timezones.value = zones.includes('UTC') ? zones : ['UTC', ...zones]
  } catch {
    timezones.value = ['UTC']
  }
})

async function save() {
  saving.value = true
  try {
    await props.saveSettings({
      timezone: localTimezone.value,
      archive_after_days: localArchiveDays.value,
      task_runner_log_level: localLogLevel.value,
    })
    emit('update:timezone', localTimezone.value)
    emit('update:archiveAfterDays', localArchiveDays.value)
    emit('update:taskRunnerLogLevel', localLogLevel.value)
    toast.success('Task management settings saved.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to save settings.')
  } finally {
    saving.value = false
  }
}

defineExpose({ isDirty })
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Task Management</h3>

    <div class="divide-y divide-gray-200">
      <!-- Timezone -->
      <div class="py-4 first:pt-0">
        <label class="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
        <select
          v-model="localTimezone"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option v-for="tz in timezones" :key="tz" :value="tz">{{ tz }}</option>
        </select>
      </div>

      <!-- Archive after days -->
      <div class="py-4">
        <label for="archive-after-days" class="block text-sm font-medium text-gray-700 mb-1">Archive after (days)</label>
        <input
          id="archive-after-days"
          v-model.number="localArchiveDays"
          type="number"
          min="1"
          class="w-24 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
      </div>

      <!-- Task Runner Log Level -->
      <div class="py-4 last:pb-0">
        <label class="block text-sm font-medium text-gray-700 mb-1">Task Runner Log Level</label>
        <select
          v-model="localLogLevel"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          data-testid="task-runner-log-level-select"
        >
          <option value="INFO">INFO</option>
          <option value="DEBUG">DEBUG</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
      </div>
    </div>

    <div class="mt-4 flex items-center gap-3">
      <button
        @click="save"
        :disabled="saving"
        class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {{ saving ? 'Saving...' : 'Save' }}
      </button>
      <span v-if="isDirty" class="text-xs text-amber-600">Unsaved changes</span>
    </div>
  </div>
</template>
