<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { fetchLlmModels, saveLlmModel, saveTaskProcessingModel, fetchTranscriptionModels, saveTranscriptionModel } from '../../composables/useApi'

const props = defineProps<{
  llmModel: string
  taskProcessingModel: string
  transcriptionModel: string
}>()

const emit = defineEmits<{
  'update:llmModel': [value: string]
  'update:taskProcessingModel': [value: string]
  'update:transcriptionModel': [value: string]
}>()

const localLlmModel = ref(props.llmModel)
const localTaskModel = ref(props.taskProcessingModel)
const localTranscriptionModel = ref(props.transcriptionModel)
const llmModels = ref<string[]>([])
const transcriptionModels = ref<string[]>([])
const llmModelsError = ref<string | null>(null)
const transcriptionModelsError = ref<string | null>(null)
const saving = ref(false)

const isDirty = computed(() =>
  localLlmModel.value !== props.llmModel
  || localTaskModel.value !== props.taskProcessingModel
  || localTranscriptionModel.value !== props.transcriptionModel
)

onMounted(async () => {
  try { llmModels.value = await fetchLlmModels() } catch { llmModelsError.value = 'Failed to load models.' }
  try { transcriptionModels.value = await fetchTranscriptionModels() } catch { transcriptionModelsError.value = 'Failed to load transcription models.' }
})

async function save() {
  saving.value = true
  try {
    await saveLlmModel(localLlmModel.value)
    await saveTaskProcessingModel(localTaskModel.value)
    await saveTranscriptionModel(localTranscriptionModel.value || null)
    emit('update:llmModel', localLlmModel.value)
    emit('update:taskProcessingModel', localTaskModel.value)
    emit('update:transcriptionModel', localTranscriptionModel.value)
    toast.success('Model settings saved.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to save model settings.')
  } finally {
    saving.value = false
  }
}

defineExpose({ isDirty })
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">LLM Models</h3>
    <div v-if="llmModelsError" class="text-sm text-red-600 mb-2">{{ llmModelsError }}</div>

    <div class="mb-4">
      <label class="block text-sm font-medium text-gray-700 mb-1">Title Generation Model</label>
      <select
        v-model="localLlmModel"
        :disabled="llmModels.length === 0"
        class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
      >
        <option v-if="llmModels.length === 0" :value="localLlmModel">{{ localLlmModel }}</option>
        <option v-for="m in llmModels" :key="m" :value="m">{{ m }}</option>
      </select>
    </div>

    <div class="mb-4">
      <label class="block text-sm font-medium text-gray-700 mb-1">Task Processing Model</label>
      <select
        v-model="localTaskModel"
        :disabled="llmModels.length === 0"
        class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
      >
        <option v-if="llmModels.length === 0" :value="localTaskModel">{{ localTaskModel }}</option>
        <option v-for="m in llmModels" :key="m" :value="m">{{ m }}</option>
      </select>
    </div>

    <div class="mb-4">
      <label class="block text-sm font-medium text-gray-700 mb-1">Transcription Model</label>
      <div v-if="transcriptionModelsError" class="text-sm text-red-600 mb-1">{{ transcriptionModelsError }}</div>
      <select
        v-model="localTranscriptionModel"
        :disabled="(transcriptionModels.length === 0 && !localTranscriptionModel) || !!transcriptionModelsError"
        class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
        data-testid="transcription-model-select"
      >
        <option value="">{{ transcriptionModels.length === 0 && !transcriptionModelsError ? 'No transcription models available' : 'Select a model to enable voice input' }}</option>
        <option v-for="m in transcriptionModels" :key="m" :value="m">{{ m }}</option>
      </select>
    </div>

    <div class="flex items-center gap-3">
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
