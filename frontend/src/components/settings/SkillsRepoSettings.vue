<script setup lang="ts">
import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'

const props = defineProps<{
  skillsGitRepo: { url?: string; branch?: string; path?: string } | null
  saveSettings: (data: Record<string, unknown>) => Promise<void>
}>()

const repoUrl = ref('')
const branch = ref('')
const skillsPath = ref('')
const saving = ref(false)

watch(() => props.skillsGitRepo, (repo) => {
  if (repo) {
    repoUrl.value = repo.url ?? ''
    branch.value = repo.branch ?? ''
    skillsPath.value = repo.path ?? ''
  } else {
    repoUrl.value = ''
    branch.value = ''
    skillsPath.value = ''
  }
}, { immediate: true })

async function save() {
  saving.value = true
  try {
    if (!repoUrl.value.trim()) {
      await props.saveSettings({ skills_git_repo: null })
    } else {
      const payload: Record<string, string> = { url: repoUrl.value.trim() }
      if (branch.value.trim()) payload.branch = branch.value.trim()
      if (skillsPath.value.trim()) payload.path = skillsPath.value.trim()
      await props.saveSettings({ skills_git_repo: payload })
    }
    toast.success('Skills repository settings saved.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Failed to save skills repository settings.')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="skills-repo-section">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Skills Repository</h3>

    <div class="space-y-4">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Repository URL</label>
        <input
          v-model="repoUrl"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="git@github.com:org/agent-skills.git"
          data-testid="skills-repo-url"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Branch</label>
        <input
          v-model="branch"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="default"
          data-testid="skills-repo-branch"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">Skills Path</label>
        <input
          v-model="skillsPath"
          type="text"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="/"
          data-testid="skills-repo-path"
        />
      </div>

      <div>
        <button
          @click="save"
          :disabled="saving"
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          data-testid="skills-repo-save"
        >
          {{ saving ? 'Saving...' : 'Save' }}
        </button>
      </div>
    </div>
  </div>
</template>
