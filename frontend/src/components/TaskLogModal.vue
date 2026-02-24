<script setup lang="ts">
import { onMounted, onUnmounted, ref, nextTick, watch, computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import TaskEventLog from './TaskEventLog.vue'
import type { TaskEvent } from './TaskEventLog.vue'

const props = defineProps<{
  taskId?: string
  title: string
  runnerLogs?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const auth = useAuthStore()
const events = ref<TaskEvent[]>([])
const finished = ref(false)
const dialogRef = ref<HTMLDialogElement | null>(null)
const logContainerRef = ref<HTMLElement | null>(null)

const isStaticMode = computed(() => !!props.runnerLogs)
const headerText = computed(() =>
  isStaticMode.value ? `Task Logs: ${props.title}` : `Live Logs: ${props.title}`
)

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
  userScrolledUp = el.scrollHeight - el.scrollTop - el.clientHeight > 50
}

watch(events, () => {
  nextTick(scrollToBottom)
}, { deep: true })

function lineCount(text: string): number {
  return text.split('\n').length
}

function parseRunnerLogs(text: string): TaskEvent[] {
  const parsed: TaskEvent[] = []
  const lines = text.split('\n')

  for (const line of lines) {
    if (!line.trim()) continue

    try {
      const obj = JSON.parse(line)
      const eventType = obj.type as string
      const eventData = (obj.data ?? {}) as Record<string, unknown>

      // Append tool_result to preceding tool_call card
      if (eventType === 'tool_result') {
        const lastEvent = parsed[parsed.length - 1]
        if (lastEvent && lastEvent.type === 'tool_call' && lastEvent.data.tool === eventData.tool) {
          const output = eventData.output as string
          lastEvent.result = {
            output,
            length: eventData.length as number,
            collapsed: lineCount(output) > 3,
          }
          continue
        }
      }

      // Determine default collapsed state
      let collapsed = false
      if (eventType === 'tool_call') {
        collapsed = true
      } else if (eventType === 'thinking' || eventType === 'reasoning') {
        const text = eventData.text as string
        collapsed = lineCount(text) > 3
      }

      parsed.push({ type: eventType, data: eventData, collapsed })
    } catch {
      parsed.push({ type: 'raw', data: { line }, collapsed: false })
    }
  }

  return parsed
}

function connect() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/api/ws/tasks/${props.taskId}/logs?token=${encodeURIComponent(auth.token ?? '')}`
  ws = new WebSocket(url)

  ws.onmessage = (wsEvent) => {
    try {
      const data = JSON.parse(wsEvent.data)
      if (data.event === 'task_event') {
        const eventType = data.type as string
        const eventData = data.data as Record<string, unknown>

        // Append tool_result to preceding tool_call card
        if (eventType === 'tool_result') {
          const lastEvent = events.value[events.value.length - 1]
          if (lastEvent && lastEvent.type === 'tool_call' && lastEvent.data.tool === eventData.tool) {
            const output = eventData.output as string
            lastEvent.result = {
              output,
              length: eventData.length as number,
              collapsed: lineCount(output) > 3,
            }
            return
          }
        }

        // Determine default collapsed state
        let collapsed = false
        if (eventType === 'tool_call') {
          collapsed = true
        } else if (eventType === 'thinking' || eventType === 'reasoning') {
          const text = eventData.text as string
          collapsed = lineCount(text) > 3
        }

        events.value.push({ type: eventType, data: eventData, collapsed })
      } else if (data.event === 'task_log_end') {
        finished.value = true
      }
    } catch {
      // Non-JSON message, append as raw
      events.value.push({ type: 'raw', data: { line: wsEvent.data }, collapsed: false })
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
  if (isStaticMode.value) {
    events.value = parseRunnerLogs(props.runnerLogs!)
  } else {
    connect()
  }
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
        <h3 class="text-sm font-semibold text-gray-800 truncate">{{ headerText }}</h3>
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
        class="flex-1 overflow-y-auto bg-gray-900 p-4 space-y-2"
        data-testid="log-container"
        @scroll="onScroll"
      >
        <p v-if="!isStaticMode && events.length === 0 && !finished" class="text-sm text-gray-500 italic">
          Waiting for logs...
        </p>

        <TaskEventLog :events="events" />

        <div
          v-if="!isStaticMode && finished"
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
