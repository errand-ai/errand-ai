<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { useAuthStore } from '../../stores/auth'

interface SkillFile {
  id: string
  path: string
  content?: string
  created_at: string
}
interface Skill {
  id: string
  name: string
  description: string
  instructions: string
  files: SkillFile[]
  created_at: string
  updated_at: string
}

const auth = useAuthStore()

const skills = ref<Skill[]>([])
const skillsLoading = ref(false)
const skillsSaving = ref(false)
const skillsError = ref<string | null>(null)
const showSkillForm = ref(false)
const editingSkillId = ref<string | null>(null)
const skillForm = ref({ name: '', description: '', instructions: '' })
const skillNameError = ref<string | null>(null)
const expandedSkillId = ref<string | null>(null)
const expandedSkillFiles = ref<SkillFile[]>([])
const filesLoading = ref(false)
const showFileForm = ref(false)
const fileForm = ref({ subdirectory: 'scripts', filename: '', content: '' })
const fileFormError = ref<string | null>(null)
const fileSaving = ref(false)
const showDeleteDialog = ref(false)
const deleteDialogRef = ref<HTMLDialogElement | null>(null)
const pendingDeleteId = ref<string | null>(null)

const descriptionCharCount = computed(() => skillForm.value.description.length)

async function skillsFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

function validateSkillNameLocal(name: string): string | null {
  if (!name) return 'Name is required'
  if (name.length > 64) return 'Name must be at most 64 characters'
  if (name !== name.toLowerCase()) return 'Name must be lowercase'
  if (/--/.test(name)) return 'Name must not contain consecutive hyphens'
  if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/.test(name)) {
    return 'Name must contain only lowercase letters, digits, and hyphens, and must not start or end with a hyphen'
  }
  return null
}

async function loadSkills() {
  skillsLoading.value = true
  skillsError.value = null
  try {
    const res = await skillsFetch('/api/skills')
    if (!res.ok) {
      skillsError.value = `Failed to load skills (HTTP ${res.status})`
      return
    }
    skills.value = await res.json()
  } catch {
    skillsError.value = 'Failed to load skills. Please check your connection.'
  } finally {
    skillsLoading.value = false
  }
}

function openAddSkill() {
  editingSkillId.value = null
  skillForm.value = { name: '', description: '', instructions: '' }
  skillNameError.value = null
  showSkillForm.value = true
}

function openEditSkill(skill: Skill) {
  editingSkillId.value = skill.id
  skillForm.value = { name: skill.name, description: skill.description, instructions: skill.instructions }
  skillNameError.value = null
  showSkillForm.value = true
}

function cancelSkillForm() {
  showSkillForm.value = false
  editingSkillId.value = null
  skillNameError.value = null
}

function onSkillNameInput() {
  const name = skillForm.value.name
  if (!name) { skillNameError.value = null; return }
  skillNameError.value = validateSkillNameLocal(name)
}

async function submitSkillForm() {
  const { name, description, instructions } = skillForm.value
  if (!name.trim() || !description.trim() || !instructions.trim()) {
    skillNameError.value = 'All fields are required.'
    return
  }
  const nameValidation = validateSkillNameLocal(name.trim())
  if (nameValidation) { skillNameError.value = nameValidation; return }
  if (description.length > 1024) {
    skillNameError.value = 'Description must be at most 1024 characters.'
    return
  }

  skillsSaving.value = true
  skillsError.value = null
  try {
    if (editingSkillId.value) {
      const res = await skillsFetch(`/api/skills/${editingSkillId.value}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: description.trim(), instructions: instructions.trim() }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        skillsError.value = data.detail || `Failed to update skill (HTTP ${res.status})`
        return
      }
    } else {
      const res = await skillsFetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), description: description.trim(), instructions: instructions.trim() }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        skillsError.value = data.detail || `Failed to create skill (HTTP ${res.status})`
        return
      }
    }
    await loadSkills()
    showSkillForm.value = false
    editingSkillId.value = null
    toast.success('Skill saved.')
  } catch {
    skillsError.value = 'Failed to save skill. Please check your connection.'
  } finally {
    skillsSaving.value = false
  }
}

function requestDeleteSkill(id: string) {
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

  skillsSaving.value = true
  skillsError.value = null
  try {
    const res = await skillsFetch(`/api/skills/${id}`, { method: 'DELETE' })
    if (!res.ok && res.status !== 204) {
      skillsError.value = `Failed to delete skill (HTTP ${res.status})`
      return
    }
    if (expandedSkillId.value === id) {
      expandedSkillId.value = null
      expandedSkillFiles.value = []
    }
    await loadSkills()
    toast.success('Skill deleted.')
  } catch {
    skillsError.value = 'Failed to delete skill. Please check your connection.'
  } finally {
    skillsSaving.value = false
  }
}

async function toggleSkillFiles(skillId: string) {
  if (expandedSkillId.value === skillId) {
    expandedSkillId.value = null
    expandedSkillFiles.value = []
    showFileForm.value = false
    return
  }
  expandedSkillId.value = skillId
  filesLoading.value = true
  try {
    const res = await skillsFetch(`/api/skills/${skillId}`)
    if (res.ok) {
      const data = await res.json()
      expandedSkillFiles.value = data.files || []
    }
  } catch {
    expandedSkillFiles.value = []
  } finally {
    filesLoading.value = false
  }
}

function groupedFiles(files: SkillFile[]) {
  const groups: Record<string, SkillFile[]> = {}
  for (const f of files) {
    const dir = f.path.split('/')[0]
    if (!groups[dir]) groups[dir] = []
    groups[dir].push(f)
  }
  return groups
}

function openAddFile() {
  fileForm.value = { subdirectory: 'scripts', filename: '', content: '' }
  fileFormError.value = null
  showFileForm.value = true
}

function cancelFileForm() {
  showFileForm.value = false
  fileFormError.value = null
}

async function submitFileForm() {
  const { subdirectory, filename, content } = fileForm.value
  if (!filename.trim()) { fileFormError.value = 'Filename is required.'; return }
  if (!content.trim()) { fileFormError.value = 'Content is required.'; return }
  if (filename.includes('/') || filename.includes('\\')) {
    fileFormError.value = 'Filename must not contain path separators.'; return
  }

  const path = `${subdirectory}/${filename.trim()}`
  fileSaving.value = true
  fileFormError.value = null
  try {
    const res = await skillsFetch(`/api/skills/${expandedSkillId.value}/files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      fileFormError.value = data.detail || `Failed to add file (HTTP ${res.status})`
      return
    }
    const detailRes = await skillsFetch(`/api/skills/${expandedSkillId.value}`)
    if (detailRes.ok) {
      const data = await detailRes.json()
      expandedSkillFiles.value = data.files || []
    }
    showFileForm.value = false
    await loadSkills()
    toast.success('File added.')
  } catch {
    fileFormError.value = 'Failed to add file. Please check your connection.'
  } finally {
    fileSaving.value = false
  }
}

async function deleteFile(skillId: string, fileId: string) {
  try {
    const res = await skillsFetch(`/api/skills/${skillId}/files/${fileId}`, { method: 'DELETE' })
    if (!res.ok && res.status !== 204) return
    const detailRes = await skillsFetch(`/api/skills/${skillId}`)
    if (detailRes.ok) {
      const data = await detailRes.json()
      expandedSkillFiles.value = data.files || []
    }
    await loadSkills()
    toast.success('File deleted.')
  } catch {
    toast.error('Failed to delete file.')
  }
}

onMounted(() => loadSkills())
</script>

<template>
  <div class="mb-6 rounded-lg bg-white p-6 shadow" data-testid="skills-section">
    <h3 class="text-lg font-semibold text-gray-800 mb-1">
      Skills
      <span class="ml-2 text-sm font-normal text-gray-500">({{ skills.length }})</span>
    </h3>
    <p class="text-sm text-gray-500 mb-3">Portable skill directories following the Agent Skills standard. Each skill includes a SKILL.md manifest and optional scripts, references, and assets.</p>
    <div v-if="skillsError" class="mb-2 text-sm text-red-600" data-testid="skills-error">{{ skillsError }}</div>

    <!-- Skill list -->
    <div v-if="skills.length > 0 && !showSkillForm" class="space-y-2 mb-3">
      <div v-for="skill in skills" :key="skill.id" class="rounded-md border border-gray-200">
        <div class="flex items-start justify-between p-3">
          <div class="flex-1 cursor-pointer" @click="toggleSkillFiles(skill.id)">
            <div class="text-sm font-medium text-gray-800">{{ skill.name }}</div>
            <div class="text-xs text-gray-500">{{ skill.description }}</div>
            <div class="text-xs text-gray-400 mt-1">{{ skill.files?.length || 0 }} file(s)</div>
          </div>
          <div class="flex gap-2 ml-3 shrink-0">
            <button @click="toggleSkillFiles(skill.id)" class="text-xs text-gray-500 hover:text-gray-700" data-testid="skill-files-toggle">{{ expandedSkillId === skill.id ? 'Hide Files' : 'Files' }}</button>
            <button @click="openEditSkill(skill)" class="text-xs text-blue-600 hover:text-blue-800" data-testid="skill-edit">Edit</button>
            <button @click="requestDeleteSkill(skill.id)" :disabled="skillsSaving" class="text-xs text-red-600 hover:text-red-800 disabled:opacity-50" data-testid="skill-delete">Delete</button>
          </div>
        </div>

        <!-- File manager (expanded) -->
        <div v-if="expandedSkillId === skill.id" class="border-t border-gray-200 p-3 bg-gray-50" data-testid="skill-files-panel">
          <div v-if="filesLoading" class="text-xs text-gray-400">Loading files...</div>
          <template v-else>
            <div v-if="expandedSkillFiles.length === 0 && !showFileForm" class="text-xs text-gray-400 mb-2">No files attached.</div>
            <div v-for="(files, dir) in groupedFiles(expandedSkillFiles)" :key="dir" class="mb-2">
              <div class="text-xs font-semibold text-gray-600 mb-1">{{ dir }}/</div>
              <div v-for="file in files" :key="file.id" class="flex items-center justify-between pl-3 py-1">
                <span class="text-xs font-mono text-gray-700">{{ file.path.split('/')[1] }}</span>
                <button @click="deleteFile(skill.id, file.id)" class="text-xs text-red-500 hover:text-red-700" data-testid="file-delete">Delete</button>
              </div>
            </div>

            <div v-if="showFileForm" class="mt-2 rounded-md border border-gray-300 p-3 space-y-2 bg-white" data-testid="file-form">
              <div v-if="fileFormError" class="text-xs text-red-600">{{ fileFormError }}</div>
              <div class="flex gap-2">
                <div>
                  <label class="block text-xs font-medium text-gray-600 mb-1">Subdirectory</label>
                  <select v-model="fileForm.subdirectory" class="rounded-md border border-gray-300 px-2 py-1 text-xs" data-testid="file-subdirectory-select">
                    <option value="scripts">scripts/</option>
                    <option value="references">references/</option>
                    <option value="assets">assets/</option>
                  </select>
                </div>
                <div class="flex-1">
                  <label class="block text-xs font-medium text-gray-600 mb-1">Filename</label>
                  <input v-model="fileForm.filename" type="text" class="w-full rounded-md border border-gray-300 px-2 py-1 text-xs" placeholder="e.g. extract.py" data-testid="file-filename-input" />
                </div>
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-600 mb-1">Content</label>
                <textarea v-model="fileForm.content" rows="4" class="w-full rounded-md border border-gray-300 p-2 text-xs font-mono" placeholder="File content..." data-testid="file-content-input"></textarea>
              </div>
              <div class="flex gap-2">
                <button @click="submitFileForm" :disabled="fileSaving" class="rounded-md bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50" data-testid="file-save">{{ fileSaving ? 'Adding...' : 'Add File' }}</button>
                <button @click="cancelFileForm" class="rounded-md border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50" data-testid="file-cancel">Cancel</button>
              </div>
            </div>

            <button v-if="!showFileForm" @click="openAddFile" class="mt-2 text-xs text-blue-600 hover:text-blue-800" data-testid="file-add">Add File</button>
          </template>
        </div>
      </div>
    </div>

    <div v-if="skills.length === 0 && !showSkillForm && !skillsLoading" class="text-sm text-gray-400 mb-3" data-testid="skills-empty-state">No skills defined yet.</div>

    <!-- Add/Edit skill form -->
    <div v-if="showSkillForm" class="rounded-md border border-gray-200 p-4 mb-3 space-y-3">
      <h4 class="text-sm font-semibold text-gray-700">{{ editingSkillId ? 'Edit Skill' : 'New Skill' }}</h4>
      <div v-if="skillNameError" class="text-sm text-red-600" data-testid="skill-name-error">{{ skillNameError }}</div>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Name</label>
        <input v-model="skillForm.name" @input="onSkillNameInput" type="text" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500" placeholder="e.g. researcher" data-testid="skill-name-input" />
        <p class="mt-1 text-xs text-gray-400">Lowercase letters, digits, and hyphens only. Max 64 characters.</p>
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Description</label>
        <input v-model="skillForm.description" type="text" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500" placeholder="Brief summary for agent discovery" data-testid="skill-description-input" />
        <p class="mt-1 text-xs" :class="descriptionCharCount > 1024 ? 'text-red-500' : 'text-gray-400'" data-testid="description-char-count">{{ descriptionCharCount }}/1024</p>
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Instructions</label>
        <textarea v-model="skillForm.instructions" rows="6" class="w-full rounded-md border border-gray-300 p-3 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500" placeholder="Full prompt instructions the agent will follow..." data-testid="skill-instructions-input"></textarea>
      </div>
      <div class="flex gap-2">
        <button @click="submitSkillForm" :disabled="skillsSaving" class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50" data-testid="skill-save">
          {{ skillsSaving ? 'Saving...' : (editingSkillId ? 'Update' : 'Add') }}
        </button>
        <button @click="cancelSkillForm" class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50" data-testid="skill-cancel">Cancel</button>
      </div>
    </div>

    <button v-if="!showSkillForm" @click="openAddSkill" class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50" data-testid="skill-add">Add Skill</button>

    <!-- Delete confirmation dialog -->
    <dialog
      ref="deleteDialogRef"
      class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
      @cancel.prevent="cancelDelete"
      @click="onDeleteDialogClick"
    >
      <div class="w-80 p-6">
        <h3 class="mb-2 text-lg font-semibold text-gray-800">Delete skill?</h3>
        <p class="mb-4 text-sm text-gray-600">This will permanently delete the skill and all its files. This action cannot be undone.</p>
        <div class="flex justify-end gap-2">
          <button type="button" class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50" @click="cancelDelete" data-testid="skill-delete-cancel">Cancel</button>
          <button type="button" class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700" @click="confirmDelete" data-testid="skill-delete-confirm">Delete</button>
        </div>
      </div>
    </dialog>
  </div>
</template>
