<script setup lang="ts">
import { inject, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import SystemPromptSettings from '../../components/settings/SystemPromptSettings.vue'
import SkillsSettings from '../../components/settings/SkillsSettings.vue'
import SkillsRepoSettings from '../../components/settings/SkillsRepoSettings.vue'
import McpServerConfigSettings from '../../components/settings/McpServerConfigSettings.vue'

const {
  systemPrompt,
  mcpServersText,
  skillsGitRepo,
  saveSettings,
} = inject<any>('settings-state')

const systemPromptRef = ref<InstanceType<typeof SystemPromptSettings> | null>(null)
const mcpConfigRef = ref<InstanceType<typeof McpServerConfigSettings> | null>(null)

const hasUnsavedChanges = computed(() =>
  systemPromptRef.value?.isDirty || mcpConfigRef.value?.isDirty
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
  <SystemPromptSettings
    ref="systemPromptRef"
    :system-prompt="systemPrompt"
    :save-settings="saveSettings"
    @update:system-prompt="systemPrompt = $event"
  />

  <SkillsSettings />

  <SkillsRepoSettings
    :skills-git-repo="skillsGitRepo"
    :save-settings="saveSettings"
  />

  <McpServerConfigSettings
    ref="mcpConfigRef"
    :mcp-servers-text="mcpServersText"
    :save-settings="saveSettings"
    @update:mcp-servers-text="mcpServersText = $event"
  />
</template>
