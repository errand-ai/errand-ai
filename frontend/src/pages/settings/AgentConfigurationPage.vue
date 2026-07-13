<script setup lang="ts">
import { inject } from 'vue'
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

// The migrated library cards (SystemPromptCard, SkillsRepoCard, McpServersCard,
// LitellmMcpCard) own their own load/save and register with <SettingsShell> for
// unsaved-changes guarding, so this page no longer tracks their dirty state.
// PluginPollIntervalSettings still reads from the shared settings-state provider,
// which SettingsPage always provides (fail fast if it is ever missing).
const { pluginPollIntervalSeconds, saveSettings } = inject<any>('settings-state')

// PluginPollIntervalSettings derives its dirty state from `initialValue`. The
// shared `saveSettings` only PUTs — it doesn't refresh settings-state — so after
// a save the section would stay "dirty" until a full reload. Wrap it to sync the
// provided ref when the poll interval is saved.
async function savePluginPollInterval(data: Record<string, unknown>) {
  await saveSettings(data)
  if ('plugin_poll_interval_seconds' in data && pluginPollIntervalSeconds) {
    pluginPollIntervalSeconds.value = data.plugin_poll_interval_seconds
  }
}
</script>

<template>
  <SystemPromptCard />

  <SkillsSettings />

  <SkillsRepoCard />

  <McpServersCard />

  <LitellmMcpCard />

  <MarketplacesSettings />

  <PluginsSettings />

  <PluginPollIntervalSettings
    :initial-value="pluginPollIntervalSeconds"
    :save-settings="savePluginPollInterval"
  />
</template>
