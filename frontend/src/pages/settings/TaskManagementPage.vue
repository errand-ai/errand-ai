<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { TaskManagementCard, TelemetryCard } from '@errand-ai/ui-components'
import LlmProviderSettings from '../../components/settings/LlmProviderSettings.vue'
import LlmModelSettings from '../../components/settings/LlmModelSettings.vue'
import type { LlmProviderData, ModelSetting } from '../../composables/useApi'

// TaskManagementCard and TelemetryCard (library) own their own state and register
// with <SettingsShell> for unsaved-changes guarding. LlmProviderSettings and
// LlmModelSettings stay local (Wave 2) and still read from settings-state.
const {
  llmModel,
  taskProcessingModel,
  transcriptionModel,
  titleGenerationTimeout,
  taskProcessingTimeout,
  transcriptionTimeout,
} = inject<any>('settings-state') ?? {}

const providerRef = ref<InstanceType<typeof LlmProviderSettings> | null>(null)
const llmModelRef = ref<InstanceType<typeof LlmModelSettings> | null>(null)

const providers = ref<LlmProviderData[]>([])

function onProvidersChanged() {
  // Refresh providers list for model selectors
  if (providerRef.value) {
    providers.value = providerRef.value.providers
  }
}

// Helper to ensure model settings are ModelSetting objects
function toModelSetting(val: any): ModelSetting {
  if (val && typeof val === 'object' && 'provider_id' in val) {
    return val as ModelSetting
  }
  // Legacy flat string or empty
  return { provider_id: null, model: typeof val === 'string' ? val : '' }
}

const hasUnsavedChanges = computed(() => !!llmModelRef.value?.isDirty)

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (hasUnsavedChanges.value) {
    e.preventDefault()
  }
}

onBeforeRouteLeave(() => {
  if (hasUnsavedChanges.value) {
    return window.confirm('You have unsaved changes. Are you sure you want to leave?')
  }
})

// Watch for provider ref becoming available and sync
watch(() => providerRef.value?.providers, (newProviders) => {
  if (newProviders) providers.value = [...newProviders]
}, { deep: true })

onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))
</script>

<template>
  <LlmProviderSettings
    ref="providerRef"
    @providers-changed="onProvidersChanged"
  />

  <LlmModelSettings
    ref="llmModelRef"
    :llm-model="toModelSetting(llmModel)"
    :task-processing-model="toModelSetting(taskProcessingModel)"
    :transcription-model="toModelSetting(transcriptionModel)"
    :title-generation-timeout="titleGenerationTimeout"
    :task-processing-timeout="taskProcessingTimeout"
    :transcription-timeout="transcriptionTimeout"
    :providers="providers"
    @update:llm-model="llmModel = $event"
    @update:task-processing-model="taskProcessingModel = $event"
    @update:transcription-model="transcriptionModel = $event"
    @update:title-generation-timeout="titleGenerationTimeout = $event"
    @update:task-processing-timeout="taskProcessingTimeout = $event"
    @update:transcription-timeout="transcriptionTimeout = $event"
  />

  <TaskManagementCard />

  <TelemetryCard />
</template>
