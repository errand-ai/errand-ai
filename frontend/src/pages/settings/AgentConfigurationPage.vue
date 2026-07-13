<script setup lang="ts">
import {
  SystemPromptCard,
  SkillsRepoCard,
  McpServersCard,
  LitellmMcpCard,
} from '@errand-ai/ui-components'
import SkillsSettings from '../../components/settings/SkillsSettings.vue'
import MarketplacesSettings from '../../components/settings/MarketplacesSettings.vue'
import PluginsSettings from '../../components/settings/PluginsSettings.vue'
import PluginPollIntervalSettings from '../../components/settings/PluginPollIntervalSettings.vue'

// The library cards and every local section on this page own their own load/save.
// PluginPollIntervalSettings self-loads its interval (post-Wave-2), so the page no
// longer injects the shared settings-state provider.
</script>

<template>
  <SystemPromptCard />

  <SkillsSettings />

  <SkillsRepoCard />

  <McpServersCard />

  <LitellmMcpCard />

  <MarketplacesSettings />

  <PluginsSettings />

  <PluginPollIntervalSettings />
</template>
