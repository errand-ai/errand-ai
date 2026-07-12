<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { toast } from 'vue-sonner'

const props = defineProps<{
  initialValue: number
  saveSettings: (data: Record<string, unknown>) => Promise<void>
}>()

const localValue = ref<string>(String(props.initialValue ?? 21600))
const saving = ref(false)
const error = ref<string | null>(null)

watch(() => props.initialValue, (next) => {
  localValue.value = String(next ?? 21600)
})

const parsed = computed(() => {
  const raw = String(localValue.value ?? '').trim()
  if (!raw) return null
  const n = Number(raw)
  if (!Number.isInteger(n) || n < 0) return null
  return n
})

const disabledHint = computed(() => parsed.value === 0)

const isDirty = computed(() => String(props.initialValue) !== String(localValue.value ?? '').trim())

async function save() {
  const value = parsed.value
  if (value === null) {
    error.value = 'Polling interval must be a non-negative integer (seconds).'
    return
  }
  saving.value = true
  error.value = null
  try {
    await props.saveSettings({ plugin_poll_interval_seconds: value })
    toast.success(value === 0 ? 'Plugin polling disabled.' : 'Polling interval saved.')
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Failed to save polling interval.'
    error.value = msg
    toast.error(msg)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow-sm" data-testid="plugin-poll-interval-section">
    <h3 class="text-lg font-semibold text-gray-800 mb-1">Plugin Update Polling</h3>
    <p class="text-sm text-gray-500 mb-3">How often the server resyncs enabled marketplaces and refreshes plugin update availability.</p>

    <div v-if="error" class="mb-2 text-sm text-red-600" data-testid="plugin-poll-error">{{ error }}</div>

    <div class="flex items-center gap-3">
      <label class="block text-xs font-medium text-gray-600">Interval (seconds)</label>
      <input
        v-model="localValue"
        type="number"
        min="0"
        step="1"
        class="w-40 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        data-testid="plugin-poll-interval-input"
      />
      <span v-if="disabledHint" class="text-xs text-amber-600" data-testid="plugin-poll-disabled-hint">Polling disabled</span>
    </div>

    <div class="mt-3 flex items-center gap-3">
      <button
        @click="save"
        :disabled="saving || !isDirty"
        class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        data-testid="plugin-poll-save"
      >
        {{ saving ? 'Saving...' : 'Save' }}
      </button>
      <span v-if="isDirty" class="text-xs text-amber-600">Unsaved changes</span>
    </div>
  </div>
</template>
