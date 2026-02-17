<script setup lang="ts">
import { inject } from 'vue'
import GitSshKeySettings from '../../components/settings/GitSshKeySettings.vue'
import McpApiKeySettings from '../../components/settings/McpApiKeySettings.vue'

const {
  mcpApiKey,
  sshPublicKey,
  gitSshHosts,
  saveSettings,
} = inject<any>('settings-state')
</script>

<template>
  <GitSshKeySettings
    :ssh-public-key="sshPublicKey"
    :git-ssh-hosts="gitSshHosts"
    :save-settings="saveSettings"
    @update:ssh-public-key="sshPublicKey = $event"
    @update:git-ssh-hosts="gitSshHosts = $event"
  />

  <McpApiKeySettings
    :mcp-api-key="mcpApiKey"
    @update:mcp-api-key="mcpApiKey = $event"
  />
</template>
