<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import {
  fetchPlugins,
  patchPlugin,
  deletePlugin,
  updatePlugin,
  installPlugin,
  fetchMarketplaces,
  fetchMarketplacePlugins,
  type Plugin,
  type Marketplace,
  type MarketplacePluginEntry,
} from '../../composables/useApi'

const plugins = ref<Plugin[]>([])
const loading = ref(false)
const expandedIds = ref<Set<string>>(new Set())
const togglingIds = ref<Set<string>>(new Set())
const updatingIds = ref<Set<string>>(new Set())

const showMarketplaceDialog = ref(false)
const marketplaceDialogRef = ref<HTMLDialogElement | null>(null)
const showManualDialog = ref(false)
const manualDialogRef = ref<HTMLDialogElement | null>(null)

const showDeleteDialog = ref(false)
const deleteDialogRef = ref<HTMLDialogElement | null>(null)
const pendingDeleteId = ref<string | null>(null)

// Marketplace install state
const enabledMarketplaces = ref<Marketplace[]>([])
const selectedMarketplaceId = ref('')
const marketplacePluginsList = ref<MarketplacePluginEntry[]>([])
const marketplacePluginsLoading = ref(false)
const selectedPluginName = ref('')
const selectedVersion = ref('')
const installing = ref(false)

// Manual install state
const manualSourceType = ref<'github' | 'git'>('github')
const manualSourceUrl = ref('')
const manualRef = ref('')
const manualAuthToken = ref('')
const manualInstalling = ref(false)
const manualError = ref<string | null>(null)

const selectedMarketplacePlugin = computed<MarketplacePluginEntry | null>(() => {
  if (!selectedPluginName.value) return null
  return marketplacePluginsList.value.find((p) => p.name === selectedPluginName.value) ?? null
})

const availableVersions = computed<string[]>(() => {
  const plugin = selectedMarketplacePlugin.value
  if (!plugin) return []
  if (plugin.available_versions && plugin.available_versions.length > 0) {
    return plugin.available_versions
  }
  if (plugin.version) return [plugin.version]
  return []
})

const previewIsUnsupported = computed(() => selectedMarketplacePlugin.value?.unsupported === true)

async function load() {
  loading.value = true
  try {
    const result = await fetchPlugins()
    plugins.value = Array.isArray(result) ? result : []
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to load plugins.')
  } finally {
    loading.value = false
  }
}

function toggleExpanded(id: string) {
  const next = new Set(expandedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedIds.value = next
}

async function togglePluginEnabled(plugin: Plugin) {
  togglingIds.value.add(plugin.id)
  try {
    const updated = await patchPlugin(plugin.id, { enabled: !plugin.enabled })
    const idx = plugins.value.findIndex((p) => p.id === plugin.id)
    if (idx >= 0) plugins.value[idx] = updated
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to toggle plugin.')
  } finally {
    togglingIds.value.delete(plugin.id)
  }
}

async function doUpdate(plugin: Plugin) {
  updatingIds.value.add(plugin.id)
  try {
    const updated = await updatePlugin(plugin.id)
    const idx = plugins.value.findIndex((p) => p.id === plugin.id)
    if (idx >= 0) plugins.value[idx] = updated
    toast.success(`Updated ${plugin.plugin_name}.`)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to update plugin.')
  } finally {
    updatingIds.value.delete(plugin.id)
  }
}

function requestDelete(id: string) {
  pendingDeleteId.value = id
  showDeleteDialog.value = true
  setTimeout(() => deleteDialogRef.value?.showModal(), 0)
}

function cancelDelete() {
  deleteDialogRef.value?.close()
  showDeleteDialog.value = false
  pendingDeleteId.value = null
}

function onDeleteDialogClick(e: MouseEvent) {
  if (e.target === deleteDialogRef.value) cancelDelete()
}

async function confirmDelete() {
  const id = pendingDeleteId.value
  deleteDialogRef.value?.close()
  showDeleteDialog.value = false
  pendingDeleteId.value = null
  if (!id) return
  try {
    await deletePlugin(id)
    await load()
    toast.success('Plugin removed.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to remove plugin.')
  }
}

// --- Marketplace install dialog ---

async function openMarketplaceDialog() {
  showMarketplaceDialog.value = true
  selectedMarketplaceId.value = ''
  selectedPluginName.value = ''
  selectedVersion.value = ''
  marketplacePluginsList.value = []
  try {
    const all = await fetchMarketplaces()
    enabledMarketplaces.value = all.filter((m) => m.enabled)
  } catch {
    enabledMarketplaces.value = []
  }
  setTimeout(() => marketplaceDialogRef.value?.showModal(), 0)
}

function closeMarketplaceDialog() {
  marketplaceDialogRef.value?.close()
  showMarketplaceDialog.value = false
}

function onMarketplaceDialogClick(e: MouseEvent) {
  if (e.target === marketplaceDialogRef.value) closeMarketplaceDialog()
}

async function onMarketplaceSelected() {
  selectedPluginName.value = ''
  selectedVersion.value = ''
  marketplacePluginsList.value = []
  if (!selectedMarketplaceId.value) return
  marketplacePluginsLoading.value = true
  try {
    marketplacePluginsList.value = await fetchMarketplacePlugins(selectedMarketplaceId.value)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to load plugins from marketplace.')
  } finally {
    marketplacePluginsLoading.value = false
  }
}

function onPluginSelected() {
  const plugin = selectedMarketplacePlugin.value
  if (!plugin) {
    selectedVersion.value = ''
    return
  }
  selectedVersion.value = availableVersions.value[0] ?? ''
}

async function confirmMarketplaceInstall() {
  if (!selectedMarketplaceId.value || !selectedPluginName.value) return
  if (previewIsUnsupported.value) return
  installing.value = true
  try {
    await installPlugin({
      marketplace_id: selectedMarketplaceId.value,
      plugin_name: selectedPluginName.value,
      version: selectedVersion.value || undefined,
    })
    toast.success(`Installed ${selectedPluginName.value}.`)
    closeMarketplaceDialog()
    await load()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to install plugin.')
  } finally {
    installing.value = false
  }
}

// --- Manual install dialog ---

async function openManualDialog() {
  manualSourceType.value = 'github'
  manualSourceUrl.value = ''
  manualRef.value = ''
  manualAuthToken.value = ''
  manualError.value = null
  showManualDialog.value = true
  setTimeout(() => manualDialogRef.value?.showModal(), 0)
}

function closeManualDialog() {
  manualDialogRef.value?.close()
  showManualDialog.value = false
}

function onManualDialogClick(e: MouseEvent) {
  if (e.target === manualDialogRef.value) closeManualDialog()
}

async function confirmManualInstall() {
  if (!manualSourceUrl.value.trim()) {
    manualError.value = 'Source URL is required.'
    return
  }
  manualInstalling.value = true
  manualError.value = null
  try {
    await installPlugin({
      source_type: manualSourceType.value,
      source_url: manualSourceUrl.value.trim(),
      ref: manualRef.value.trim() || null,
      auth_token: manualAuthToken.value || null,
    })
    toast.success('Plugin installed.')
    closeManualDialog()
    await load()
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Failed to install plugin.'
    manualError.value = msg
    toast.error(msg)
  } finally {
    manualInstalling.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow-sm" data-testid="plugins-section">
    <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
      <div>
        <h3 class="text-lg font-semibold text-gray-800">
          Plugins
          <span class="ml-2 text-sm font-normal text-gray-500">({{ plugins.length }})</span>
        </h3>
        <p class="text-sm text-gray-500">Versioned bundles that contribute skills and MCP servers.</p>
      </div>
      <div class="flex gap-2">
        <button
          @click="openMarketplaceDialog"
          class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          data-testid="plugin-install-marketplace"
        >
          Install from Marketplace
        </button>
        <button
          @click="openManualDialog"
          class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          data-testid="plugin-install-manual"
        >
          Install Manually
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-sm text-gray-400">Loading plugins...</div>

    <div v-else-if="plugins.length === 0" class="text-sm text-gray-400" data-testid="plugins-empty-state">
      No plugins installed.
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="plugin in plugins"
        :key="plugin.id"
        class="rounded-md border border-gray-200"
        :data-testid="`plugin-card-${plugin.id}`"
      >
        <div class="flex items-start justify-between gap-3 p-3">
          <button
            type="button"
            class="flex-1 text-left min-w-0"
            @click="toggleExpanded(plugin.id)"
            :data-testid="`plugin-toggle-expand-${plugin.id}`"
          >
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-sm font-medium text-gray-800">{{ plugin.plugin_name }}</span>
              <span class="text-xs text-gray-500">v{{ plugin.installed_version }}</span>
              <span class="text-xs text-gray-400">
                from {{ plugin.marketplace_name ?? (plugin.marketplace_id ? 'marketplace' : 'manual') }}
              </span>
              <span
                v-if="plugin.update_available && plugin.latest_available_version"
                class="inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700"
                :data-testid="`plugin-update-badge-${plugin.id}`"
              >
                Update: v{{ plugin.latest_available_version }}
              </span>
              <span
                v-if="(plugin.skill_conflicts?.length ?? 0) > 0"
                class="inline-block rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700"
                :data-testid="`plugin-conflict-badge-${plugin.id}`"
              >
                Skill conflict
              </span>
            </div>
            <div class="text-xs text-gray-400 mt-1">
              {{ plugin.skills.length }} skill{{ plugin.skills.length === 1 ? '' : 's' }}
              ·
              {{ plugin.mcp_servers.length }} MCP server{{ plugin.mcp_servers.length === 1 ? '' : 's' }}
            </div>
          </button>

          <div class="flex items-center gap-3 shrink-0">
            <button
              v-if="plugin.update_available"
              @click="doUpdate(plugin)"
              :disabled="updatingIds.has(plugin.id)"
              class="rounded-md border border-amber-300 px-2 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-50"
              :data-testid="`plugin-update-${plugin.id}`"
            >
              {{ updatingIds.has(plugin.id) ? 'Updating...' : 'Update' }}
            </button>
            <label class="flex items-center gap-1.5 text-xs text-gray-600">
              <input
                type="checkbox"
                :checked="plugin.enabled"
                :disabled="togglingIds.has(plugin.id)"
                @change="togglePluginEnabled(plugin)"
                class="h-4 w-4 rounded-sm border-gray-300 text-blue-600 focus:ring-blue-500"
                :data-testid="`plugin-toggle-${plugin.id}`"
              />
              Enabled
            </label>
            <button
              @click="requestDelete(plugin.id)"
              class="text-xs text-red-600 hover:text-red-800"
              :data-testid="`plugin-delete-${plugin.id}`"
            >
              Remove
            </button>
          </div>
        </div>

        <div
          v-if="expandedIds.has(plugin.id)"
          class="border-t border-gray-100 bg-gray-50 px-3 py-2 space-y-2"
          :data-testid="`plugin-details-${plugin.id}`"
        >
          <div v-if="plugin.skills.length > 0">
            <div class="text-xs font-semibold text-gray-600 mb-1">Skills</div>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="skill in plugin.skills"
                :key="skill"
                class="inline-block rounded-full bg-gray-200 px-2 py-0.5 text-xs text-gray-700"
              >{{ skill }}</span>
            </div>
          </div>

          <div v-if="plugin.mcp_servers.length > 0">
            <div class="text-xs font-semibold text-gray-600 mb-1">MCP Servers</div>
            <ul class="space-y-0.5 text-xs text-gray-700">
              <li v-for="server in plugin.mcp_servers" :key="server.raw">
                <span class="font-mono">{{ server.raw }}</span>
                <span class="text-gray-400"> → </span>
                <span class="font-mono">{{ server.namespaced }}</span>
              </li>
            </ul>
          </div>

          <div v-if="plugin.ignored_artifacts && plugin.ignored_artifacts.length > 0">
            <div class="text-xs font-semibold text-gray-600 mb-1">Ignored artifacts</div>
            <div class="text-xs text-gray-500">
              {{ plugin.ignored_artifacts.map((a) => `${a.count} ${a.type}`).join(', ') }}
            </div>
          </div>

          <div v-if="plugin.skill_conflicts && plugin.skill_conflicts.length > 0">
            <div class="text-xs font-semibold text-red-700 mb-1">Skill conflicts</div>
            <ul class="space-y-0.5 text-xs text-red-700">
              <li v-for="conflict in plugin.skill_conflicts" :key="conflict.skill">
                <span class="font-mono">{{ conflict.skill }}</span>
                also defined by <span class="font-medium">{{ conflict.other }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- Install from Marketplace dialog -->
    <dialog
      ref="marketplaceDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50 w-full max-w-lg"
      @cancel.prevent="closeMarketplaceDialog"
      @click="onMarketplaceDialogClick"
    >
      <div v-if="showMarketplaceDialog" class="p-6 space-y-4" data-testid="plugin-marketplace-dialog">
        <h3 class="text-lg font-semibold text-gray-800">Install from Marketplace</h3>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Marketplace</label>
          <select
            v-model="selectedMarketplaceId"
            @change="onMarketplaceSelected"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            data-testid="plugin-marketplace-select"
          >
            <option value="">Select marketplace</option>
            <option v-for="m in enabledMarketplaces" :key="m.id" :value="m.id">{{ m.name }}</option>
          </select>
          <p v-if="enabledMarketplaces.length === 0" class="mt-1 text-xs text-gray-400">No enabled marketplaces — enable one above first.</p>
        </div>

        <div v-if="selectedMarketplaceId">
          <label class="block text-xs font-medium text-gray-600 mb-1">Plugin</label>
          <select
            v-model="selectedPluginName"
            @change="onPluginSelected"
            :disabled="marketplacePluginsLoading"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            data-testid="plugin-marketplace-plugin-select"
          >
            <option value="">{{ marketplacePluginsLoading ? 'Loading...' : 'Select plugin' }}</option>
            <option v-for="p in marketplacePluginsList" :key="p.name" :value="p.name">{{ p.name }}</option>
          </select>
        </div>

        <div v-if="selectedMarketplacePlugin && availableVersions.length > 0">
          <label class="block text-xs font-medium text-gray-600 mb-1">Version</label>
          <select
            v-model="selectedVersion"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            data-testid="plugin-marketplace-version-select"
          >
            <option v-for="v in availableVersions" :key="v" :value="v">{{ v }}</option>
          </select>
        </div>

        <div v-if="selectedMarketplacePlugin" class="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2" data-testid="plugin-marketplace-preview">
          <div v-if="selectedMarketplacePlugin.description" class="text-xs text-gray-600">
            {{ selectedMarketplacePlugin.description }}
          </div>
          <div v-if="(selectedMarketplacePlugin.skills?.length ?? 0) > 0">
            <div class="text-xs font-semibold text-gray-600">Skills</div>
            <div class="flex flex-wrap gap-1 mt-0.5">
              <span
                v-for="skill in selectedMarketplacePlugin.skills"
                :key="skill"
                class="inline-block rounded-full bg-gray-200 px-2 py-0.5 text-xs text-gray-700"
              >{{ skill }}</span>
            </div>
          </div>
          <div v-if="(selectedMarketplacePlugin.mcp_servers?.length ?? 0) > 0">
            <div class="text-xs font-semibold text-gray-600">MCP servers</div>
            <div class="text-xs text-gray-700">{{ selectedMarketplacePlugin.mcp_servers!.join(', ') }}</div>
          </div>
          <div v-if="previewIsUnsupported" class="text-xs text-red-600" data-testid="plugin-marketplace-unsupported">
            This plugin uses an unsupported source format.
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-2">
          <button
            type="button"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            @click="closeMarketplaceDialog"
            data-testid="plugin-marketplace-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            :disabled="installing || !selectedMarketplaceId || !selectedPluginName || previewIsUnsupported"
            :title="previewIsUnsupported ? 'Unsupported plugin source' : ''"
            @click="confirmMarketplaceInstall"
            data-testid="plugin-marketplace-confirm"
          >
            {{ installing ? 'Installing...' : 'Install' }}
          </button>
        </div>
      </div>
    </dialog>

    <!-- Install Manually dialog -->
    <dialog
      ref="manualDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50 w-full max-w-lg"
      @cancel.prevent="closeManualDialog"
      @click="onManualDialogClick"
    >
      <div v-if="showManualDialog" class="p-6 space-y-4" data-testid="plugin-manual-dialog">
        <h3 class="text-lg font-semibold text-gray-800">Install Manually</h3>

        <div v-if="manualError" class="text-sm text-red-600" data-testid="plugin-manual-error">{{ manualError }}</div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Source type</label>
          <div class="flex gap-4">
            <label class="flex items-center gap-1.5 text-xs text-gray-600">
              <input type="radio" value="github" v-model="manualSourceType" class="text-blue-600" data-testid="plugin-manual-source-github" />
              GitHub (owner/repo)
            </label>
            <label class="flex items-center gap-1.5 text-xs text-gray-600">
              <input type="radio" value="git" v-model="manualSourceType" class="text-blue-600" data-testid="plugin-manual-source-git" />
              Git URL
            </label>
          </div>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Source URL</label>
          <input
            v-model="manualSourceUrl"
            type="text"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            :placeholder="manualSourceType === 'github' ? 'owner/repo' : 'https://...'"
            data-testid="plugin-manual-source-url"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Ref or version (optional)</label>
          <input
            v-model="manualRef"
            type="text"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            placeholder="main, v0.5.0, ..."
            data-testid="plugin-manual-ref"
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">Bearer token (optional)</label>
          <input
            v-model="manualAuthToken"
            type="password"
            autocomplete="off"
            class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            placeholder="Optional Authorization: Bearer header"
            data-testid="plugin-manual-auth-token"
          />
        </div>

        <div class="flex justify-end gap-2 pt-2">
          <button
            type="button"
            class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
            @click="closeManualDialog"
            data-testid="plugin-manual-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-md bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            :disabled="manualInstalling"
            @click="confirmManualInstall"
            data-testid="plugin-manual-confirm"
          >
            {{ manualInstalling ? 'Installing...' : 'Install' }}
          </button>
        </div>
      </div>
    </dialog>

    <!-- Remove confirmation dialog -->
    <dialog
      ref="deleteDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelDelete"
      @click="onDeleteDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Remove plugin?</h3>
        <p class="mb-4 text-sm text-gray-600">The plugin's cache will be removed. Any profile referencing it will silently skip the missing plugin.</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50" @click="cancelDelete" data-testid="plugin-delete-cancel">Cancel</button>
          <button type="button" class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700" @click="confirmDelete" data-testid="plugin-delete-confirm">Remove</button>
        </div>
      </div>
    </dialog>
  </div>
</template>
