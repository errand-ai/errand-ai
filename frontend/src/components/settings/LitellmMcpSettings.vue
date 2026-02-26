<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { fetchLitellmMcpServers, type LitellmMcpResponse } from '../../composables/useApi'

const props = defineProps<{
  saveSettings: (data: Record<string, unknown>) => Promise<void>
}>()

const loading = ref(true)
const refreshing = ref(false)
const saving = ref(false)
const data = ref<LitellmMcpResponse | null>(null)
const localEnabled = ref<Set<string>>(new Set())
const expandedServers = ref<Set<string>>(new Set())

const available = computed(() => data.value?.available ?? false)

const isDirty = computed(() => {
  if (!data.value) return false
  const original = new Set(data.value.enabled)
  if (original.size !== localEnabled.value.size) return true
  for (const alias of original) {
    if (!localEnabled.value.has(alias)) return true
  }
  return false
})

async function load() {
  try {
    const resp = await fetchLitellmMcpServers()
    data.value = resp
    localEnabled.value = new Set(resp.enabled)
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

async function refresh() {
  refreshing.value = true
  try {
    const resp = await fetchLitellmMcpServers()
    data.value = resp
    localEnabled.value = new Set(resp.enabled)
  } catch {
    toast.error('Failed to refresh MCP servers.')
  } finally {
    refreshing.value = false
  }
}

function toggle(alias: string) {
  const next = new Set(localEnabled.value)
  if (next.has(alias)) {
    next.delete(alias)
  } else {
    next.add(alias)
  }
  localEnabled.value = next
}

function toggleExpand(alias: string) {
  const next = new Set(expandedServers.value)
  if (next.has(alias)) {
    next.delete(alias)
  } else {
    next.add(alias)
  }
  expandedServers.value = next
}

async function save() {
  saving.value = true
  try {
    await props.saveSettings({ litellm_mcp_servers: [...localEnabled.value] })
    if (data.value) {
      data.value = { ...data.value, enabled: [...localEnabled.value] }
    }
    toast.success('LiteLLM MCP servers saved.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to save.')
  } finally {
    saving.value = false
  }
}

onMounted(load)

defineExpose({ isDirty })
</script>

<template>
  <div v-if="loading" class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="litellm-mcp-loading">
    <div class="h-5 w-56 rounded bg-gray-200 animate-pulse mb-3"></div>
    <div class="h-4 w-full rounded bg-gray-200 animate-pulse"></div>
  </div>

  <div v-else-if="available && data" class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="litellm-mcp-settings">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-lg font-semibold text-gray-800">MCP Servers (via LiteLLM)</h3>
      <button
        @click="refresh"
        :disabled="refreshing"
        data-testid="litellm-mcp-refresh"
        class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
      >
        {{ refreshing ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <div v-if="Object.keys(data.servers).length === 0" class="text-sm text-gray-500">
      No MCP servers configured in LiteLLM.
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="(server, alias) in data.servers"
        :key="alias"
        class="rounded-md border border-gray-200"
        :data-testid="`litellm-server-${alias}`"
      >
        <div class="flex items-center gap-3 p-3">
          <input
            type="checkbox"
            :checked="localEnabled.has(String(alias))"
            @change="toggle(String(alias))"
            :data-testid="`litellm-toggle-${alias}`"
            class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <button
            @click="toggleExpand(String(alias))"
            class="flex flex-1 items-center justify-between text-left"
          >
            <div>
              <span class="font-medium text-gray-800">{{ alias }}</span>
              <span v-if="server.description" class="ml-2 text-sm text-gray-500">{{ server.description }}</span>
            </div>
            <span class="text-xs text-gray-400">{{ server.tools?.length || 0 }} tool{{ (server.tools?.length || 0) === 1 ? '' : 's' }}</span>
          </button>
        </div>

        <div
          v-if="expandedServers.has(String(alias))"
          class="border-t border-gray-100 bg-gray-50 px-3 py-2"
          :data-testid="`litellm-tools-${alias}`"
        >
          <div v-if="server.tools?.length" class="flex flex-wrap gap-1">
            <span
              v-for="tool in server.tools"
              :key="tool"
              class="inline-block rounded-full bg-gray-200 px-2 py-0.5 text-xs text-gray-700"
            >
              {{ tool }}
            </span>
          </div>
          <span v-else class="text-xs text-gray-400">No tools</span>
        </div>
      </div>
    </div>

    <div class="mt-3 flex items-center gap-3">
      <button
        @click="save"
        :disabled="saving || !isDirty"
        data-testid="litellm-mcp-save"
        class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {{ saving ? 'Saving...' : 'Save' }}
      </button>
      <span v-if="isDirty" class="text-xs text-amber-600">Unsaved changes</span>
    </div>
  </div>
</template>
