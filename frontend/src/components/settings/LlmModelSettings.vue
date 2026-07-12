<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchProviderModels,
  saveLlmModelsAndTimeouts,
  type LlmProviderData,
  type ModelInfo,
  type ModelSetting,
} from '../../composables/useApi'

const props = defineProps<{
  llmModel: ModelSetting
  taskProcessingModel: ModelSetting
  transcriptionModel: ModelSetting
  titleGenerationTimeout: number
  taskProcessingTimeout: number
  transcriptionTimeout: number
  providers: LlmProviderData[]
}>()

const emit = defineEmits<{
  'update:llmModel': [value: ModelSetting]
  'update:taskProcessingModel': [value: ModelSetting]
  'update:transcriptionModel': [value: ModelSetting]
  'update:titleGenerationTimeout': [value: number]
  'update:taskProcessingTimeout': [value: number]
  'update:transcriptionTimeout': [value: number]
}>()

// Local state for each model selector
const llmProviderId = ref(props.llmModel.provider_id || '')
const llmModelName = ref(props.llmModel.model || '')
const taskProviderId = ref(props.taskProcessingModel.provider_id || '')
const taskModelName = ref(props.taskProcessingModel.model || '')
const transcriptionProviderId = ref(props.transcriptionModel.provider_id || '')
const transcriptionModelName = ref(props.transcriptionModel.model || '')
const localTitleTimeout = ref(props.titleGenerationTimeout)
const localTaskTimeout = ref(props.taskProcessingTimeout)
const localTranscriptionTimeout = ref(props.transcriptionTimeout)

// Models lists per role
const llmModels = ref<ModelInfo[]>([])
const taskModels = ref<ModelInfo[]>([])
const transcriptionModels = ref<ModelInfo[]>([])

const saving = ref(false)

function isReasoningModel(modelName: string, models: ModelInfo[]): boolean {
  const m = models.find(item => item.id === modelName)
  return m?.supports_reasoning === true
}

function isNonReasoningModel(modelName: string, models: ModelInfo[]): boolean {
  const m = models.find(item => item.id === modelName)
  return m?.supports_reasoning === false
}

function getProvider(id: string): LlmProviderData | undefined {
  return props.providers.find(p => p.id === id)
}

function isUnknownProvider(id: string): boolean {
  const p = getProvider(id)
  return p?.provider_type === 'unknown'
}

function isLitellmProvider(id: string): boolean {
  const p = getProvider(id)
  return p?.provider_type === 'litellm'
}

async function loadModels(providerId: string, target: typeof llmModels, mode?: string) {
  if (!providerId) { target.value = []; return }
  const provider = getProvider(providerId)
  if (!provider || provider.provider_type === 'unknown') { target.value = []; return }
  try {
    target.value = await fetchProviderModels(providerId, mode)
  } catch {
    target.value = []
  }
}

// Watch provider changes to reload models
watch(() => llmProviderId.value, (id, oldId) => {
  if (oldId !== undefined) llmModelName.value = ''
  loadModels(id, llmModels)
}, { immediate: true })

watch(() => taskProviderId.value, (id, oldId) => {
  if (oldId !== undefined) taskModelName.value = ''
  loadModels(id, taskModels)
}, { immediate: true })

watch(() => transcriptionProviderId.value, (id, oldId) => {
  if (oldId !== undefined) transcriptionModelName.value = ''
  const mode = isLitellmProvider(id) ? 'audio_transcription' : undefined
  loadModels(id, transcriptionModels, mode)
}, { immediate: true })

// Re-populate models when providers list changes (initial load)
watch(() => props.providers, () => {
  if (llmProviderId.value) loadModels(llmProviderId.value, llmModels)
  if (taskProviderId.value) loadModels(taskProviderId.value, taskModels)
  if (transcriptionProviderId.value) {
    const mode = isLitellmProvider(transcriptionProviderId.value) ? 'audio_transcription' : undefined
    loadModels(transcriptionProviderId.value, transcriptionModels, mode)
  }
})

const isDirty = computed(() => {
  return llmProviderId.value !== (props.llmModel.provider_id || '')
    || llmModelName.value !== (props.llmModel.model || '')
    || taskProviderId.value !== (props.taskProcessingModel.provider_id || '')
    || taskModelName.value !== (props.taskProcessingModel.model || '')
    || transcriptionProviderId.value !== (props.transcriptionModel.provider_id || '')
    || transcriptionModelName.value !== (props.transcriptionModel.model || '')
    || localTitleTimeout.value !== props.titleGenerationTimeout
    || localTaskTimeout.value !== props.taskProcessingTimeout
    || localTranscriptionTimeout.value !== props.transcriptionTimeout
})

function isPositiveInt(value: number): boolean {
  return Number.isInteger(value) && value >= 1
}

async function save() {
  if (!isPositiveInt(localTitleTimeout.value)
    || !isPositiveInt(localTaskTimeout.value)
    || !isPositiveInt(localTranscriptionTimeout.value)
  ) {
    toast.error('Timeouts must be positive integers (seconds).')
    return
  }
  saving.value = true
  try {
    const llmSetting: ModelSetting = { provider_id: llmProviderId.value || null, model: llmModelName.value }
    const taskSetting: ModelSetting = { provider_id: taskProviderId.value || null, model: taskModelName.value }
    const transcSetting: ModelSetting | null = transcriptionProviderId.value && transcriptionModelName.value
      ? { provider_id: transcriptionProviderId.value, model: transcriptionModelName.value }
      : null

    // Single PUT for atomic save — avoids partial-update state if any field fails.
    await saveLlmModelsAndTimeouts({
      llm_model: llmSetting,
      task_processing_model: taskSetting,
      transcription_model: transcSetting,
      title_generation_timeout: localTitleTimeout.value,
      task_processing_timeout: localTaskTimeout.value,
      transcription_timeout: localTranscriptionTimeout.value,
    })

    emit('update:llmModel', llmSetting)
    emit('update:taskProcessingModel', taskSetting)
    emit('update:transcriptionModel', transcSetting || { provider_id: null, model: '' })
    emit('update:titleGenerationTimeout', localTitleTimeout.value)
    emit('update:taskProcessingTimeout', localTaskTimeout.value)
    emit('update:transcriptionTimeout', localTranscriptionTimeout.value)
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
  <div class="mb-6 rounded-lg bg-white p-6 shadow-sm">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">LLM Models</h3>

    <div v-if="providers.length === 0" class="text-sm text-gray-500 mb-4">
      No providers configured. Add a provider above to select models.
    </div>

    <!-- Title Generation -->
    <div class="mb-6">
      <label class="block text-sm font-medium text-gray-700 mb-1">Title Generation Model</label>
      <div class="flex gap-2">
        <select
          v-model="llmProviderId"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option value="">Select provider</option>
          <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <input
          v-if="isUnknownProvider(llmProviderId)"
          v-model="llmModelName"
          type="text"
          placeholder="Enter model name"
          class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        <select
          v-else
          v-model="llmModelName"
          :disabled="!llmProviderId || llmModels.length === 0"
          class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
        >
          <option value="">{{ llmModels.length === 0 ? 'Loading models...' : 'Select model' }}</option>
          <option v-for="m in llmModels" :key="m.id" :value="m.id">{{ m.id }}</option>
        </select>
      </div>
      <p
        v-if="isReasoningModel(llmModelName, llmModels)"
        class="mt-1 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-sm px-2 py-1"
        data-testid="llm-reasoning-warning"
      >
        This is a reasoning model. It may be slower and less reliable for structured output tasks like title generation. Consider using a non-reasoning model.
      </p>
      <div class="mt-2">
        <label class="block text-xs font-medium text-gray-600 mb-1">Timeout (seconds)</label>
        <input
          v-model.number="localTitleTimeout"
          type="number"
          min="1"
          step="1"
          class="w-32 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          data-testid="title-generation-timeout-input"
        />
      </div>
    </div>

    <!-- Default Task Processing -->
    <div class="mb-6">
      <label class="block text-sm font-medium text-gray-700 mb-1">Default Task Processing Model</label>
      <div class="flex gap-2">
        <select
          v-model="taskProviderId"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option value="">Select provider</option>
          <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <input
          v-if="isUnknownProvider(taskProviderId)"
          v-model="taskModelName"
          type="text"
          placeholder="Enter model name"
          class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        <select
          v-else
          v-model="taskModelName"
          :disabled="!taskProviderId || taskModels.length === 0"
          class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
        >
          <option value="">{{ taskModels.length === 0 ? 'Loading models...' : 'Select model' }}</option>
          <option v-for="m in taskModels" :key="m.id" :value="m.id">{{ m.id }}</option>
        </select>
      </div>
      <p
        v-if="isNonReasoningModel(taskModelName, taskModels)"
        class="mt-1 text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-sm px-2 py-1"
        data-testid="task-non-reasoning-warning"
      >
        This is not a reasoning model. Reasoning models are recommended for task processing to support complex workflows and tool calling. Consider using a reasoning model.
      </p>
      <div class="mt-2">
        <label class="block text-xs font-medium text-gray-600 mb-1">Timeout (seconds)</label>
        <input
          v-model.number="localTaskTimeout"
          type="number"
          min="1"
          step="1"
          class="w-32 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          data-testid="task-processing-timeout-input"
        />
        <p class="mt-1 text-xs text-gray-500">Per-profile overrides supersede this default.</p>
      </div>
    </div>

    <!-- Transcription -->
    <div class="mb-4">
      <label class="block text-sm font-medium text-gray-700 mb-1">Transcription Model</label>
      <div class="flex gap-2">
        <select
          v-model="transcriptionProviderId"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option value="">Select provider</option>
          <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <input
          v-if="isUnknownProvider(transcriptionProviderId)"
          v-model="transcriptionModelName"
          type="text"
          placeholder="Enter model name"
          class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        <select
          v-else
          v-model="transcriptionModelName"
          :disabled="!transcriptionProviderId"
          class="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
          data-testid="transcription-model-select"
        >
          <option value="">{{ transcriptionModels.length === 0 ? 'Select a model to enable voice input' : 'Select model' }}</option>
          <option v-for="m in transcriptionModels" :key="m.id" :value="m.id">{{ m.id }}</option>
        </select>
      </div>
      <div class="mt-2">
        <label class="block text-xs font-medium text-gray-600 mb-1">Timeout (seconds)</label>
        <input
          v-model.number="localTranscriptionTimeout"
          type="number"
          min="1"
          step="1"
          class="w-32 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          data-testid="transcription-timeout-input"
        />
      </div>
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
