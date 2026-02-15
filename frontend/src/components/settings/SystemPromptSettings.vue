<script setup lang="ts">
import { ref, computed } from 'vue'
import { toast } from 'vue-sonner'

const props = defineProps<{
  systemPrompt: string
  saveSettings: (data: Record<string, unknown>) => Promise<void>
}>()

const emit = defineEmits<{
  'update:systemPrompt': [value: string]
}>()

const localPrompt = ref(props.systemPrompt)
const saving = ref(false)

const isDirty = computed(() => localPrompt.value !== props.systemPrompt)

async function save() {
  saving.value = true
  try {
    await props.saveSettings({ system_prompt: localPrompt.value })
    emit('update:systemPrompt', localPrompt.value)
    toast.success('System prompt saved.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to save system prompt.')
  } finally {
    saving.value = false
  }
}

defineExpose({ isDirty })
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">System Prompt</h3>
    <textarea
      v-model="localPrompt"
      rows="6"
      class="w-full rounded-md border border-gray-300 p-3 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
      placeholder="Enter the system prompt for the LLM..."
    ></textarea>
    <div class="mt-3 flex items-center gap-3">
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
