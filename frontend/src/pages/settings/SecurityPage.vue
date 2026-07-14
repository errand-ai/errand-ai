<script setup lang="ts">
import GitSshKeySettings from '../../components/settings/GitSshKeySettings.vue'
import McpApiKeySettings from '../../components/settings/McpApiKeySettings.vue'

// Both server-admin cards self-load their own state (post-Wave-2), so this page
// no longer injects or threads the shared settings-state provider.
</script>

<template>
  <GitSshKeySettings />

  <McpApiKeySettings />
</template>
