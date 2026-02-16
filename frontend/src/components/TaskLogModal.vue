<script setup lang="ts">
import { onMounted, onUnmounted, ref, nextTick, watch } from 'vue'
import { useAuthStore } from '../stores/auth'

const props = defineProps<{
  taskId: string
  title: string
}>()

const emit = defineEmits<{
  close: []
}>()

const auth = useAuthStore()
const lines = ref<string[]>([])
const finished = ref(false)
const dialogRef = ref<HTMLDialogElement | null>(null)
const logContainerRef = ref<HTMLElement | null>(null)

let ws: WebSocket | null = null
let userScrolledUp = false

function scrollToBottom() {
  if (userScrolledUp) return
  const el = logContainerRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

function onScroll() {
  const el = logContainerRef.value
  if (!el) return
  // If user scrolled more than 50px from bottom, they've scrolled up
  userScrolledUp = el.scrollHeight - el.scrollTop - el.clientHeight > 50
}

watch(lines, () => {
  nextTick(scrollToBottom)
}, { deep: true })

function connect() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/api/ws/tasks/${props.taskId}/logs?token=${encodeURIComponent(auth.token ?? '')}`
  ws = new WebSocket(url)

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.event === 'task_log') {
        lines.value.push(data.line)
      } else if (data.event === 'task_log_end') {
        finished.value = true
      }
    } catch {
      // Non-JSON message, append as-is
      lines.value.push(event.data)
    }
  }

  ws.onclose = () => {
    if (!finished.value) {
      finished.value = true
    }
  }
}

function disconnect() {
  if (ws) {
    ws.close()
    ws = null
  }
}

function closeModal() {
  disconnect()
  emit('close')
}

function onDialogClick(e: MouseEvent) {
  if (e.target === dialogRef.value) {
    closeModal()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    closeModal()
  }
}

onMounted(() => {
  dialogRef.value?.showModal()
  connect()
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  disconnect()
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <dialog
    ref="dialogRef"
    class="w-full max-w-4xl rounded-lg p-0 shadow-xl backdrop:bg-black/50"
    @click="onDialogClick"
    @cancel.prevent="closeModal"
  >
    <div class="flex flex-col" style="height: 70vh;">
      <div class="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <h3 class="text-sm font-semibold text-gray-800 truncate">Live Logs: {{ title }}</h3>
        <button
          class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          title="Close"
          @click="closeModal"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
          </svg>
        </button>
      </div>
      <div
        ref="logContainerRef"
        class="flex-1 overflow-y-auto bg-gray-900 p-4"
        @scroll="onScroll"
      >
        <p v-if="lines.length === 0 && !finished" class="text-sm text-gray-500 italic">
          Waiting for logs...
        </p>
        <pre
          v-else
          class="whitespace-pre-wrap break-words text-xs leading-5 text-gray-200 font-mono"
          data-testid="log-output"
        >{{ lines.join('') }}</pre>
        <div
          v-if="finished"
          class="mt-3 inline-flex items-center gap-1.5 rounded bg-gray-700 px-2 py-1 text-xs text-gray-300"
          data-testid="task-finished-indicator"
        >
          <span class="inline-block h-2 w-2 rounded-full bg-green-400"></span>
          Task finished
        </div>
      </div>
    </div>
  </dialog>
</template>
