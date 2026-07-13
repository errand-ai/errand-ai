<script setup lang="ts">
import { useRouter } from 'vue-router'
import { SettingsShell } from '@errand-ai/ui-components'
import type { SettingsSection } from '@errand-ai/ui-components'

const router = useRouter()

// Section ids map 1:1 to the child route path segment / route name (`settings-<id>`).
// <SettingsShell> derives the active section from the current route and emits
// `section-change` on navigation; we translate that into a router push.
//
// Post-Wave-2: every settings card (library and remaining server-admin locals)
// loads and saves its own state, so this page no longer provides a shared
// `settings-state` object nor tracks any per-setting refs — it is purely the
// navigation shell.
const sections: SettingsSection[] = [
  { id: 'agent', label: 'Agent Configuration' },
  { id: 'tasks', label: 'Task Management' },
  { id: 'security', label: 'Security' },
  { id: 'profiles', label: 'Task Profiles' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'task-generators', label: 'Task Generators' },
  { id: 'cloud', label: 'Cloud Service' },
  { id: 'users', label: 'User Management' },
]

function onSectionChange(id: string) {
  router.push({ name: `settings-${id}` })
}
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <SettingsShell :sections="sections" @section-change="onSectionChange">
      <router-view />
    </SettingsShell>
  </div>
</template>
