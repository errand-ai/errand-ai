<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import LlmProviderSettings from '../../components/settings/LlmProviderSettings.vue'
import LlmModelSettings from '../../components/settings/LlmModelSettings.vue'
import TaskManagementSettings from '../../components/settings/TaskManagementSettings.vue'
import TelemetrySettings from '../../components/settings/TelemetrySettings.vue'
import type { LlmProviderData, ModelSetting } from '../../composables/useApi'

const {
  llmModel,
  taskProcessingModel,
  transcriptionModel,
  llmTimeout,
  timezoneValue,
  archiveAfterDays,
  maxConcurrentTasks,
  taskRunnerLogLevel,
  saveSettings,
} = inject<any>('settings-state')

const providerRef = ref<InstanceType<typeof LlmProviderSettings> | null>(null)
const llmModelRef = ref<InstanceType<typeof LlmModelSettings> | null>(null)
const taskMgmtRef = ref<InstanceType<typeof TaskManagementSettings> | null>(null)
const telemetryRef = ref<InstanceType<typeof TelemetrySettings> | null>(null)

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

const hasUnsavedChanges = computed(() =>
  llmModelRef.value?.isDirty || taskMgmtRef.value?.isDirty || telemetryRef.value?.isDirty
)

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
    :llm-timeout="llmTimeout"
    :providers="providers"
    @update:llm-model="llmModel = $event"
    @update:task-processing-model="taskProcessingModel = $event"
    @update:transcription-model="transcriptionModel = $event"
    @update:llm-timeout="llmTimeout = $event"
  />

  <TaskManagementSettings
    ref="taskMgmtRef"
    :timezone="timezoneValue"
    :archive-after-days="archiveAfterDays"
    :max-concurrent-tasks="maxConcurrentTasks"
    :task-runner-log-level="taskRunnerLogLevel"
    :save-settings="saveSettings"
    @update:timezone="timezoneValue = $event"
    @update:archive-after-days="archiveAfterDays = $event"
    @update:max-concurrent-tasks="maxConcurrentTasks = $event"
    @update:task-runner-log-level="taskRunnerLogLevel = $event"
  />

  <TelemetrySettings ref="telemetryRef" />
</template>
