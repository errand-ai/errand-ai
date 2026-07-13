<script setup lang="ts">
import {
  GoogleWorkspaceCard,
  CloudStorageCard,
  JiraCredentialCard,
  PlatformsCard,
} from '@errand-ai/ui-components'

// All four cards come from @errand-ai/ui-components and are gated by the server's
// advertised capabilities (google_workspace, cloud_storage, jira, platforms).
</script>

<template>
  <GoogleWorkspaceCard />
  <CloudStorageCard />
  <JiraCredentialCard />
  <PlatformsCard />
</template>
