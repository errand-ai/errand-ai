<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchProviderModels,
  saveLlmModel,
  saveLlmTimeout,
  saveTaskProcessingModel,
  saveTranscriptionModel,
  type LlmProviderData,
  type ModelSetting,
} from '../../composables/useApi'

const props = defineProps<{
  llmModel: ModelSetting
  taskProcessingModel: ModelSetting
  transcriptionModel: ModelSetting
  llmTimeout: number
  providers: LlmProviderData[]
}>()

const emit = defineEmits<{
  'update:llmModel': [value: ModelSetting]
  'update:taskProcessingModel': [value: ModelSetting]
  'update:transcriptionModel': [value: ModelSetting]
  'update:llmTimeout': [value: number]
}>()

// Local state for each model selector
const llmProviderId = ref(props.llmModel.provider_id || '')
const llmModelName = ref(props.llmModel.model || '')
const taskProviderId = ref(props.taskProcessingModel.provider_id || '')
const taskModelName = ref(props.taskProcessingModel.model || '')
const transcriptionProviderId = ref(props.transcriptionModel.provider_id || '')
const transcriptionModelName = ref(props.transcriptionModel.model || '')
const localLlmTimeout = ref(props.llmTimeout)

// Models lists per role
const llmModels = ref<string[]>([])
const taskModels = ref<string[]>([])
const transcriptionModels = ref<string[]>([])

const saving = ref(false)

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
    || localLlmTimeout.value !== props.llmTimeout
})

async function save() {
  saving.value = true
  try {
    const llmSetting: ModelSetting = { provider_id: llmProviderId.value || null, model: llmModelName.value }
    const taskSetting: ModelSetting = { provider_id: taskProviderId.value || null, model: taskModelName.value }
    const transcSetting: ModelSetting | null = transcriptionProviderId.value && transcriptionModelName.value
      ? { provider_id: transcriptionProviderId.value, model: transcriptionModelName.value }
      : null

    await saveLlmModel(llmSetting)
    await saveTaskProcessingModel(taskSetting)
    await saveTranscriptionModel(transcSetting)
    await saveLlmTimeout(localLlmTimeout.value)

    emit('update:llmModel', llmSetting)
    emit('update:taskProcessingModel', taskSetting)
    emit('update:transcriptionModel', transcSetting || { provider_id: null, model: '' })
    emit('update:llmTimeout', localLlmTimeout.value)
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

    <div v-if="providers.length === 0" class="text-sm text-gray-500 mb-4">
      No providers configured. Add a provider above to select models.
    </div>

    <!-- Title Generation Model -->
    <div class="mb-4">
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
          <option v-for="m in llmModels" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
    </div>

    <!-- Default Model (Task Processing) -->
    <div class="mb-4">
      <label class="block text-sm font-medium text-gray-700 mb-1">Default Model</label>
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
          <option v-for="m in taskModels" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
    </div>

    <!-- Transcription Model -->
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
          <option v-for="m in transcriptionModels" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
    </div>

    <!-- LLM Timeout -->
    <div class="mb-4">
      <label class="block text-sm font-medium text-gray-700 mb-1">LLM Timeout (seconds)</label>
      <input
        v-model.number="localLlmTimeout"
        type="number"
        min="1"
        class="w-32 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        data-testid="llm-timeout-input"
      />
      <p class="mt-1 text-xs text-gray-500">How long to wait for LLM responses. Increase for local models that need loading time.</p>
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
