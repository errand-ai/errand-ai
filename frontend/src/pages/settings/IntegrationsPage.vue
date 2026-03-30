<script setup lang="ts">
import PlatformSettings from '../../components/settings/PlatformSettings.vue'
import CloudStorageIntegration from '../../components/settings/CloudStorageIntegration.vue'
import JiraCredentialCard from '../../components/settings/JiraCredentialCard.vue'
</script>

<template>
  <CloudStorageIntegration />
  <JiraCredentialCard />
  <PlatformSettings />
</template>
