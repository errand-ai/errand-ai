<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { toast } from 'vue-sonner'

const {
  settingsMetadata,
  saveSettings,
} = inject<any>('settings-state')

const localEnabled = ref(true)
const saving = ref(false)
const loaded = ref(false)

// Watch for metadata to populate local state
const meta = computed(() => settingsMetadata.value?.telemetry_enabled)
const isReadonly = computed(() => meta.value?.readonly === true)

// Initialize from metadata when available
import { watch } from 'vue'
watch(() => meta.value, (m) => {
  if (m && !loaded.value) {
    localEnabled.value = m.value !== false && m.value !== 'false'
    loaded.value = true
  }
}, { immediate: true })

const isDirty = computed(() => {
  if (!meta.value) return false
  const current = meta.value.value !== false && meta.value.value !== 'false'
  return localEnabled.value !== current
})

async function save() {
  saving.value = true
  try {
    await saveSettings({ telemetry_enabled: localEnabled.value })
    toast.success('Telemetry settings saved.')
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
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Usage Telemetry</h3>

    <div class="py-2">
      <div class="flex items-center justify-between">
        <div class="flex-1">
          <label class="block text-sm font-medium text-gray-700">Send anonymous usage data</label>
          <p class="text-xs text-gray-500 mt-1">
            Help improve Errand by sending anonymous usage statistics such as task counts and deployment type. No personal data or task content is collected.
          </p>
          <p v-if="isReadonly" class="text-xs text-amber-600 mt-1">
            Controlled by TELEMETRY_ENABLED environment variable
          </p>
        </div>
        <button
          type="button"
          role="switch"
          :aria-checked="localEnabled"
          :disabled="isReadonly"
          :class="[
            localEnabled ? 'bg-blue-600' : 'bg-gray-200',
            isReadonly ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
            'relative ml-4 inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
          ]"
          @click="!isReadonly && (localEnabled = !localEnabled)"
        >
          <span
            :class="[
              localEnabled ? 'translate-x-5' : 'translate-x-0',
              'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
            ]"
          />
        </button>
      </div>
    </div>

    <div v-if="isDirty" class="mt-4 flex items-center gap-3">
      <button
        @click="save"
        :disabled="saving"
        class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {{ saving ? 'Saving...' : 'Save' }}
      </button>
      <span class="text-xs text-amber-600">Unsaved changes</span>
    </div>
  </div>
</template>
