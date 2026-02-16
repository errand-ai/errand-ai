<script setup lang="ts">
import { ref, computed } from 'vue'
import { toast } from 'vue-sonner'

const props = defineProps<{
  mcpServersText: string
  saveSettings: (data: Record<string, unknown>) => Promise<void>
}>()

const emit = defineEmits<{
  'update:mcpServersText': [value: string]
}>()

const localText = ref(props.mcpServersText)
const expanded = ref(false)
const saving = ref(false)
const mcpError = ref<string | null>(null)

const isDirty = computed(() => localText.value !== props.mcpServersText)

function validateMcpConfig(parsed: unknown): string | null {
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return 'MCP configuration must be a JSON object.'
  }
  const config = parsed as Record<string, unknown>
  const servers = config.mcpServers
  if (servers === undefined) {
    if (Object.keys(config).length === 0) return null
    return 'MCP configuration must have a "mcpServers" key.'
  }
  if (typeof servers !== 'object' || servers === null || Array.isArray(servers)) {
    return '"mcpServers" must be an object mapping server names to configurations.'
  }
  const serverEntries = servers as Record<string, unknown>
  for (const [name, entry] of Object.entries(serverEntries)) {
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
      return `Server '${name}' must be an object with a 'url' field.`
    }
    const serverEntry = entry as Record<string, unknown>
    if ('command' in serverEntry || 'args' in serverEntry) {
      return `Only HTTP Streaming MCP servers are supported. Server '${name}' uses STDIO transport (command/args) which is not allowed.`
    }
    if (!('url' in serverEntry) || typeof serverEntry.url !== 'string' || !serverEntry.url) {
      return `Server '${name}' is missing required 'url' field.`
    }
  }
  return null
}

async function save() {
  mcpError.value = null
  let parsed: unknown
  const trimmed = localText.value.trim()
  if (trimmed === '') {
    parsed = {}
  } else {
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      mcpError.value = 'Invalid JSON. Please check syntax and try again.'
      return
    }
  }
  const validationError = validateMcpConfig(parsed)
  if (validationError) { mcpError.value = validationError; return }

  saving.value = true
  try {
    await props.saveSettings({ mcp_servers: parsed })
    emit('update:mcpServersText', localText.value)
    toast.success('MCP configuration saved.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to save MCP configuration.')
  } finally {
    saving.value = false
  }
}

defineExpose({ isDirty })
</script>

<template>
  <div class="rounded-lg bg-white p-6 shadow">
    <button
      @click="expanded = !expanded"
      class="flex w-full items-center justify-between text-left"
    >
      <h3 class="text-lg font-semibold text-gray-800">MCP Server Configuration</h3>
      <svg
        :class="{ 'rotate-180': expanded }"
        class="h-5 w-5 text-gray-500 transition-transform"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>
    <div v-if="expanded" class="mt-3">
      <div v-if="mcpError" class="mb-2 text-sm text-red-600">{{ mcpError }}</div>
      <textarea
        v-model="localText"
        rows="10"
        class="w-full rounded-md border border-gray-300 p-3 font-mono text-xs focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        placeholder='{"servers": []}'
      ></textarea>
      <div class="mt-3 flex items-center gap-3">
        <button
          @click="save"
          :disabled="saving"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {{ saving ? 'Saving...' : 'Save MCP Config' }}
        </button>
        <span v-if="isDirty" class="text-xs text-amber-600">Unsaved changes</span>
      </div>
    </div>
  </div>
</template>
