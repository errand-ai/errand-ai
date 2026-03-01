<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import type { PlatformCredentialField, TaskProfile } from '../../composables/useApi'
import { fetchTaskProfiles } from '../../composables/useApi'

const props = withDefaults(defineProps<{
  schema: PlatformCredentialField[]
  saving: boolean
  editableOnly?: boolean
  initialValues?: Record<string, string>
}>(), {
  editableOnly: false,
  initialValues: () => ({}),
})

const emit = defineEmits<{
  save: [credentials: Record<string, string>]
}>()

const fields = ref<Record<string, string>>({})
const profiles = ref<TaskProfile[]>([])

// When editableOnly is true, filter schema to only editable fields
const effectiveSchema = computed(() => {
  if (!props.editableOnly) return props.schema
  return props.schema.filter(f => f.editable)
})

onMounted(async () => {
  if (effectiveSchema.value.some(f => f.type === 'profile_select')) {
    try {
      profiles.value = await fetchTaskProfiles()
    } catch {
      profiles.value = []
    }
  }
})

// Find the mode selector field (type === 'select' with options) if any
const modeField = computed(() => effectiveSchema.value.find(f => f.type === 'select' && f.options?.length))

watch(() => effectiveSchema.value, (schema) => {
  if (!schema) return
  const init: Record<string, string> = {}
  for (const field of schema) {
    if (props.initialValues[field.key] !== undefined) {
      init[field.key] = props.initialValues[field.key]
    } else {
      init[field.key] = field.type === 'select' && field.options?.length ? field.options[0].value : (field.default ?? '')
    }
  }
  fields.value = init
}, { immediate: true })

const visibleFields = computed(() => {
  return effectiveSchema.value.filter(field => {
    // Hide the mode selector from the regular field list — it's rendered as a toggle
    if (field.type === 'select' && field.options?.length) return false
    if (!field.auth_mode) return true
    if (!modeField.value) return true
    return fields.value[modeField.value.key] === field.auth_mode
  })
})

function onSubmit() {
  const creds: Record<string, string> = {}
  // Include the mode field value
  if (modeField.value) {
    creds[modeField.value.key] = fields.value[modeField.value.key]
  }
  for (const field of visibleFields.value) {
    creds[field.key] = fields.value[field.key]
  }
  emit('save', creds)
}
</script>

<template>
  <form @submit.prevent="onSubmit" class="space-y-3" data-testid="credential-form">
    <!-- Mode toggle (rendered as pill buttons instead of a dropdown) -->
    <div v-if="modeField" class="mb-1">
      <label class="block text-sm font-medium text-gray-700 mb-2">{{ modeField.label }}</label>
      <div
        class="inline-flex rounded-md border border-gray-300 overflow-hidden"
        :data-testid="`cred-input-${modeField.key}`"
      >
        <button
          v-for="opt in modeField.options"
          :key="opt.value"
          type="button"
          @click="fields[modeField.key] = opt.value"
          class="px-4 py-1.5 text-sm font-medium transition-colors"
          :class="fields[modeField.key] === opt.value
            ? 'bg-blue-600 text-white'
            : 'bg-white text-gray-600 hover:bg-gray-50'"
          :data-testid="`cred-toggle-${opt.value}`"
        >
          {{ opt.label }}
        </button>
      </div>
    </div>

    <!-- Regular fields (filtered by active mode) -->
    <div v-for="field in visibleFields" :key="field.key">
      <label :for="`cred-${field.key}`" class="block text-sm font-medium text-gray-700 mb-1">
        {{ field.label }}
        <span v-if="field.required" class="text-red-500">*</span>
      </label>

      <!-- Textarea -->
      <textarea
        v-if="field.type === 'textarea'"
        :id="`cred-${field.key}`"
        v-model="fields[field.key]"
        :required="field.required"
        :placeholder="field.label"
        rows="4"
        class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        :data-testid="`cred-input-${field.key}`"
      />

      <!-- Text input -->
      <input
        v-else-if="field.type === 'text'"
        :id="`cred-${field.key}`"
        v-model="fields[field.key]"
        type="text"
        :required="field.required"
        :placeholder="field.label"
        class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        :data-testid="`cred-input-${field.key}`"
      />

      <!-- Profile select dropdown -->
      <select
        v-else-if="field.type === 'profile_select'"
        :id="`cred-${field.key}`"
        v-model="fields[field.key]"
        :required="field.required"
        class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        :data-testid="`cred-input-${field.key}`"
      >
        <option v-if="profiles.length === 0" value="" disabled>No task profiles configured. Create a profile first.</option>
        <template v-else>
          <option value="">Select a profile</option>
          <option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option>
        </template>
      </select>

      <!-- Password input (default) -->
      <input
        v-else
        :id="`cred-${field.key}`"
        v-model="fields[field.key]"
        type="password"
        :required="field.required"
        :placeholder="field.label"
        class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        :data-testid="`cred-input-${field.key}`"
      />

      <!-- Help text -->
      <p v-if="field.help_text" class="mt-1 text-xs text-gray-500">{{ field.help_text }}</p>
    </div>
    <button
      type="submit"
      :disabled="saving"
      class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      data-testid="credential-save"
    >
      {{ saving ? (editableOnly ? 'Saving...' : 'Testing...') : (editableOnly ? 'Save' : 'Test & Save') }}
    </button>
  </form>
</template>
