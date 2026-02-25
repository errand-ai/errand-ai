<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import LlmModelSettings from '../../components/settings/LlmModelSettings.vue'
import TaskManagementSettings from '../../components/settings/TaskManagementSettings.vue'

const {
  llmModel,
  taskProcessingModel,
  transcriptionModel,
  llmTimeout,
  timezoneValue,
  archiveAfterDays,
  taskRunnerLogLevel,
  saveSettings,
} = inject<any>('settings-state')

const llmModelRef = ref<InstanceType<typeof LlmModelSettings> | null>(null)
const taskMgmtRef = ref<InstanceType<typeof TaskManagementSettings> | null>(null)

const hasUnsavedChanges = computed(() =>
  llmModelRef.value?.isDirty || taskMgmtRef.value?.isDirty
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

onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload))
</script>

<template>
  <LlmModelSettings
    ref="llmModelRef"
    :llm-model="llmModel"
    :task-processing-model="taskProcessingModel"
    :transcription-model="transcriptionModel"
    :llm-timeout="llmTimeout"
    @update:llm-model="llmModel = $event"
    @update:task-processing-model="taskProcessingModel = $event"
    @update:transcription-model="transcriptionModel = $event"
    @update:llm-timeout="llmTimeout = $event"
  />

  <TaskManagementSettings
    ref="taskMgmtRef"
    :timezone="timezoneValue"
    :archive-after-days="archiveAfterDays"
    :task-runner-log-level="taskRunnerLogLevel"
    :save-settings="saveSettings"
    @update:timezone="timezoneValue = $event"
    @update:archive-after-days="archiveAfterDays = $event"
    @update:task-runner-log-level="taskRunnerLogLevel = $event"
  />
</template>
