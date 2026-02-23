<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { PlatformCredentialField } from '../../composables/useApi'

const props = defineProps<{
  schema: PlatformCredentialField[]
  saving: boolean
}>()

const emit = defineEmits<{
  save: [credentials: Record<string, string>]
}>()

const fields = ref<Record<string, string>>({})

watch(() => props.schema, (schema) => {
  if (!schema) return
  const init: Record<string, string> = {}
  for (const field of schema) {
    init[field.key] = field.type === 'select' && field.options?.length ? field.options[0].value : ''
  }
  fields.value = init
}, { immediate: true })

const visibleFields = computed(() => {
  return props.schema.filter(field => {
    if (!field.auth_mode) return true
    const modeField = props.schema.find(f => f.key === 'auth_mode')
    if (!modeField) return true
    return fields.value['auth_mode'] === field.auth_mode
  })
})

function onSubmit() {
  const creds: Record<string, string> = {}
  for (const field of visibleFields.value) {
    creds[field.key] = fields.value[field.key]
  }
  emit('save', creds)
}
</script>

<template>
  <form @submit.prevent="onSubmit" class="space-y-3" data-testid="credential-form">
    <div v-for="field in visibleFields" :key="field.key">
      <label :for="`cred-${field.key}`" class="block text-sm font-medium text-gray-700 mb-1">
        {{ field.label }}
        <span v-if="field.required" class="text-red-500">*</span>
      </label>

      <!-- Select dropdown -->
      <select
        v-if="field.type === 'select'"
        :id="`cred-${field.key}`"
        v-model="fields[field.key]"
        :required="field.required"
        class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        :data-testid="`cred-input-${field.key}`"
      >
        <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>

      <!-- Textarea -->
      <textarea
        v-else-if="field.type === 'textarea'"
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
    </div>
    <button
      type="submit"
      :disabled="saving"
      class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      data-testid="credential-save"
    >
      {{ saving ? 'Testing...' : 'Test & Save' }}
    </button>
  </form>
</template>
