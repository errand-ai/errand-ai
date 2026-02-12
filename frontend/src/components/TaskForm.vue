<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useTaskStore } from '../stores/tasks'
import { fetchTranscriptionStatus, transcribeAudio } from '../composables/useApi'

const store = useTaskStore()
const input = ref('')
const error = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

// Voice input state
const transcriptionEnabled = ref(false)
const isRecording = ref(false)
const isTranscribing = ref(false)
const recordingSeconds = ref(0)
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
let recordingTimer: ReturnType<typeof setInterval> | null = null

const supportsMediaRecorder = computed(() => typeof MediaRecorder !== 'undefined')
const showMicButton = computed(() => supportsMediaRecorder.value && transcriptionEnabled.value)

onMounted(async () => {
  try {
    const status = await fetchTranscriptionStatus()
    transcriptionEnabled.value = status.enabled
  } catch {
    transcriptionEnabled.value = false
  }
})

onUnmounted(() => {
  if (recordingTimer) clearInterval(recordingTimer)
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    mediaRecorder.value.stop()
  }
})

async function toggleRecording() {
  if (isRecording.value) {
    stopRecording()
  } else {
    await startRecording()
  }
}

async function startRecording() {
  error.value = ''
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream)
    audioChunks.value = []

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.value.push(e.data)
    }

    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      if (recordingTimer) {
        clearInterval(recordingTimer)
        recordingTimer = null
      }
      recordingSeconds.value = 0
      isRecording.value = false

      const blob = new Blob(audioChunks.value, { type: recorder.mimeType || 'audio/webm' })
      await sendForTranscription(blob)
    }

    recorder.start()
    mediaRecorder.value = recorder
    isRecording.value = true
    recordingSeconds.value = 0
    recordingTimer = setInterval(() => { recordingSeconds.value++ }, 1000)
  } catch {
    error.value = 'Microphone access is required for voice input'
  }
}

function stopRecording() {
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    mediaRecorder.value.stop()
  }
}

async function sendForTranscription(blob: Blob) {
  isTranscribing.value = true
  error.value = ''
  try {
    const text = await transcribeAudio(blob)
    if (input.value.trim()) {
      input.value = input.value + ' ' + text
    } else {
      input.value = text
    }
    inputRef.value?.focus()
  } catch {
    error.value = 'Voice transcription failed. Please try again or type your task.'
  } finally {
    isTranscribing.value = false
  }
}

async function submit() {
  const trimmed = input.value.trim()
  if (!trimmed) {
    error.value = 'Task cannot be empty'
    return
  }
  error.value = ''
  try {
    await store.addTask(trimmed)
    input.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create task'
  }
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<template>
  <form @submit.prevent="submit" class="flex gap-2">
    <input
      ref="inputRef"
      v-model="input"
      type="text"
      placeholder="New task..."
      class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
    />
    <button
      v-if="showMicButton"
      type="button"
      :disabled="isTranscribing"
      @click="toggleRecording"
      :class="[
        'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
        isRecording
          ? 'bg-red-600 text-white animate-pulse'
          : 'bg-gray-200 text-gray-700 hover:bg-gray-300',
        isTranscribing ? 'opacity-50 cursor-not-allowed' : ''
      ]"
      :title="isRecording ? 'Stop recording' : 'Start voice input'"
      data-testid="mic-button"
    >
      <template v-if="isTranscribing">
        <svg class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </template>
      <template v-else-if="isRecording">
        {{ formatTime(recordingSeconds) }}
      </template>
      <template v-else>
        <svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
          <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
        </svg>
      </template>
    </button>
    <button
      type="submit"
      class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
    >
      Add Task
    </button>
  </form>
  <p v-if="error" class="mt-1 text-sm text-red-600">{{ error }}</p>
</template>
