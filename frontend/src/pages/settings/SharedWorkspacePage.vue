<script setup lang="ts">
import { SharedWorkspaceCard } from '@errand-ai/ui-components'

// Thin mount point. The library card owns its own load (via getWorkspaceStatus)
// and renders the read-only deployment config + gateway health readout. Enabling
// the workspace per profile happens in the Task Profiles edit modal.
</script>

<template>
  <SharedWorkspaceCard />
</template>
