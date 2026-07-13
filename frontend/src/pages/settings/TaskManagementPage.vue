<script setup lang="ts">
import {
  LlmProviderCard,
  LlmModelCard,
  TaskManagementCard,
  TelemetryCard,
} from '@errand-ai/ui-components'

// All four cards come from @errand-ai/ui-components. They own their own load/save
// and register with <SettingsShell> for unsaved-changes guarding, so this page is
// purely declarative — no local state, inject, or route-leave plumbing.
</script>

<template>
  <LlmProviderCard />

  <LlmModelCard />

  <TaskManagementCard />

  <TelemetryCard />
</template>
