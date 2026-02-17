<script setup lang="ts">
import { ref, watch } from 'vue'
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
    init[field.key] = ''
  }
  fields.value = init
}, { immediate: true })

function onSubmit() {
  emit('save', { ...fields.value })
}
</script>

<template>
  <form @submit.prevent="onSubmit" class="space-y-3" data-testid="credential-form">
    <div v-for="field in schema" :key="field.key">
      <label :for="`cred-${field.key}`" class="block text-sm font-medium text-gray-700 mb-1">
        {{ field.label }}
        <span v-if="field.required" class="text-red-500">*</span>
      </label>
      <input
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
