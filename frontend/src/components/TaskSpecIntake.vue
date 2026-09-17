<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  answerTaskSpec,
  cancelTaskSpec,
  confirmTaskSpec,
  fetchTaskSpecs,
  startTaskSpec,
  TaskSpecError,
  type TaskData,
  type TaskSpecDraft,
} from '../composables/useApi'

// Task intake with clarification. A description becomes a draft; the draft
// either asks a few questions or shows what will run, and only Run creates the
// task. Every call goes through /api/task-specs — nothing here classifies.

const emit = defineEmits<{
  'task-created': [task: TaskData]
}>()

const input = ref('')
const error = ref('')
const busy = ref(false)
const draft = ref<TaskSpecDraft | null>(null)
const answers = ref<Record<string, string>>({})
const inputRef = ref<HTMLTextAreaElement | null>(null)

const drafting = computed(() => draft.value?.status === 'drafting')
const preview = computed(() => draft.value?.spec_preview)

// Earlier exchanges, shown as context. The first turn is the description
// itself, and while questions are open the latest assistant turn is those
// questions, which are shown as fields instead.
const history = computed(() => {
  if (!draft.value) return []
  const turns = draft.value.conversation.slice(1).filter((t) => t.role !== 'system')
  return drafting.value ? turns.slice(0, -1) : turns
})

const whenLabel = computed(() => {
  const p = preview.value
  if (!p) return ''
  if (p.category === 'immediate') return 'Now'
  return p.execute_at ? new Date(p.execute_at).toLocaleString() : 'Not set'
})

function autoResize() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function setDraft(next: TaskSpecDraft | null) {
  draft.value = next
  answers.value = {}
}

function reset() {
  setDraft(null)
  input.value = ''
  nextTick(() => {
    if (inputRef.value) inputRef.value.style.height = 'auto'
    inputRef.value?.focus()
  })
}

async function run<T>(action: () => Promise<T>): Promise<T | undefined> {
  if (busy.value) return undefined
  error.value = ''
  busy.value = true
  try {
    return await action()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Something went wrong'
    // Expired, or already run or cancelled elsewhere: this draft is over, so
    // go back to a fresh form rather than offer buttons that cannot work.
    if (e instanceof TaskSpecError && (e.status === 404 || e.status === 409)) setDraft(null)
    return undefined
  } finally {
    busy.value = false
  }
}

async function start() {
  const trimmed = input.value.trim()
  if (!trimmed) {
    error.value = 'Task cannot be empty'
    return
  }
  const started = await run(() => startTaskSpec(trimmed))
  if (started) setDraft(started)
}

async function submitAnswers() {
  const current = draft.value
  if (!current) return
  const next = await run(() => answerTaskSpec(current.id, answers.value))
  if (next) setDraft(next)
}

async function confirm() {
  const current = draft.value
  if (!current) return
  const task = await run(() => confirmTaskSpec(current.id))
  if (task) {
    reset()
    emit('task-created', task)
  }
}

async function cancel() {
  const current = draft.value
  if (!current) return
  const cancelled = await run(() => cancelTaskSpec(current.id))
  if (cancelled) reset()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    start()
  }
}

function onTranscription(text: string) {
  input.value = input.value.trim() ? `${input.value} ${text}` : text
  nextTick(() => autoResize())
  inputRef.value?.focus()
}

// Pick up where the user left off: a draft outlives a closed tab.
onMounted(async () => {
  try {
    const pending = await fetchTaskSpecs()
    if (pending.length && !draft.value) setDraft(pending[0])
  } catch {
    // Resuming is a convenience; the form works without it.
  }
})
</script>

<template>
  <div data-testid="task-spec-intake">
    <form v-if="!draft" class="flex items-start gap-2" @submit.prevent="start">
      <textarea
        ref="inputRef"
        v-model="input"
        placeholder="New task..."
        rows="1"
        :disabled="busy"
        data-testid="intake-input"
        class="flex-1 resize-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
        style="max-height: 144px; overflow-y: auto"
        @input="autoResize"
        @keydown="onKeydown"
      />
      <slot name="voice" :on-transcription="onTranscription" />
      <button
        type="submit"
        :disabled="busy"
        data-testid="intake-start"
        class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {{ busy ? 'Thinking…' : 'Add Task' }}
      </button>
    </form>

    <section v-else class="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" data-testid="intake-draft">
      <p class="text-xs uppercase tracking-wide text-gray-400">New task</p>
      <p class="mb-3 whitespace-pre-wrap text-sm text-gray-700" data-testid="intake-original">{{ draft.input }}</p>

      <ol v-if="history.length" class="mb-3 space-y-1 border-l-2 border-gray-100 pl-3 text-sm" data-testid="intake-history">
        <li
          v-for="(turn, i) in history"
          :key="i"
          class="whitespace-pre-wrap"
          :class="turn.role === 'assistant' ? 'text-gray-500' : 'text-gray-800'"
        >{{ turn.content }}</li>
      </ol>

      <form v-if="drafting" class="space-y-3" data-testid="intake-questions" @submit.prevent="submitAnswers">
        <p class="text-sm font-medium text-gray-800">
          A few questions before I set up <span class="font-semibold">{{ preview?.title }}</span>
          <span class="ml-1 text-xs font-normal text-gray-400">(round {{ draft.round + 1 }} of {{ draft.max_rounds }})</span>
        </p>
        <div v-for="q in draft.questions" :key="q.id">
          <label :for="`q-${q.id}`" class="mb-1 block text-sm text-gray-700">{{ q.text }}</label>
          <select
            v-if="q.kind === 'choice' && q.choices?.length"
            :id="`q-${q.id}`"
            v-model="answers[q.id]"
            :disabled="busy"
            :data-testid="`answer-${q.id}`"
            class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="" disabled>Choose one</option>
            <option v-for="choice in q.choices" :key="choice" :value="choice">{{ choice }}</option>
          </select>
          <input
            v-else
            :id="`q-${q.id}`"
            v-model="answers[q.id]"
            type="text"
            :disabled="busy"
            :data-testid="`answer-${q.id}`"
            class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            type="submit"
            :disabled="busy"
            data-testid="intake-answer"
            class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {{ busy ? 'Thinking…' : 'Submit answers' }}
          </button>
          <button
            type="button"
            :disabled="busy"
            data-testid="intake-just-run"
            class="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            @click="confirm"
          >
            Just run it
          </button>
          <button
            type="button"
            :disabled="busy"
            data-testid="intake-cancel"
            class="rounded-lg px-4 py-2 text-sm text-gray-500 hover:text-red-600 disabled:opacity-50"
            @click="cancel"
          >
            Cancel
          </button>
        </div>
      </form>

      <div v-else-if="preview" data-testid="intake-preview">
        <p class="mb-2 text-sm font-medium text-gray-800">I'll do this — run it?</p>
        <dl class="mb-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg bg-gray-50 p-3 text-sm">
          <dt class="text-gray-500">Title</dt>
          <dd class="font-medium text-gray-900" data-testid="preview-title">{{ preview.title }}</dd>
          <dt class="text-gray-500">When</dt>
          <dd class="text-gray-900">{{ whenLabel }}</dd>
          <template v-if="preview.repeat_interval">
            <dt class="text-gray-500">Repeats</dt>
            <dd class="text-gray-900">{{ preview.repeat_interval }}</dd>
          </template>
          <template v-if="preview.profile">
            <dt class="text-gray-500">Profile</dt>
            <dd class="text-gray-900">{{ preview.profile }}</dd>
          </template>
          <dt class="text-gray-500">Task</dt>
          <dd class="whitespace-pre-wrap text-gray-900" data-testid="preview-description">{{ preview.description }}</dd>
        </dl>
        <div
          v-if="draft.questions_unresolved && draft.questions.length"
          class="mb-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800"
          data-testid="intake-unresolved"
        >
          <p class="mb-1 font-medium">Still open — the task will use its best judgement:</p>
          <ul class="list-disc pl-5">
            <li v-for="q in draft.questions" :key="q.id">{{ q.text }}</li>
          </ul>
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            :disabled="busy"
            data-testid="intake-run"
            class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            @click="confirm"
          >
            Run
          </button>
          <button
            type="button"
            :disabled="busy"
            data-testid="intake-cancel"
            class="rounded-lg px-4 py-2 text-sm text-gray-500 hover:text-red-600 disabled:opacity-50"
            @click="cancel"
          >
            Cancel
          </button>
        </div>
      </div>
    </section>
    <p v-if="error" class="mt-1 text-sm text-red-600" data-testid="form-error">{{ error }}</p>
  </div>
</template>
