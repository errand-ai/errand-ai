<script setup lang="ts">
import { inject } from 'vue'
import PlatformSettings from '../../components/settings/PlatformSettings.vue'
import LitellmMcpSettings from '../../components/settings/LitellmMcpSettings.vue'

const { saveSettings } = inject<any>('settings-state')
</script>

<template>
  <PlatformSettings />
  <LitellmMcpSettings :save-settings="saveSettings" />
</template>
