<script setup lang="ts">
import { CloudStorageCard, JiraCredentialCard } from '@errand-ai/ui-components'
import PlatformSettings from '../../components/settings/PlatformSettings.vue'
import GoogleWorkspaceIntegration from '../../components/settings/GoogleWorkspaceIntegration.vue'
</script>

<template>
  <GoogleWorkspaceIntegration />
  <CloudStorageCard />
  <JiraCredentialCard />
  <PlatformSettings />
</template>
