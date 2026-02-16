<script setup lang="ts">
import { onMounted, onUnmounted, ref, nextTick, watch } from 'vue'
import { useAuthStore } from '../stores/auth'

interface TaskEvent {
  type: string
  data: Record<string, unknown>
  collapsed?: boolean
  result?: { output: string; length: number; collapsed: boolean }
}

const props = defineProps<{
  taskId: string
  title: string
}>()

const emit = defineEmits<{
  close: []
}>()

const auth = useAuthStore()
const events = ref<TaskEvent[]>([])
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
  userScrolledUp = el.scrollHeight - el.scrollTop - el.clientHeight > 50
}

watch(events, () => {
  nextTick(scrollToBottom)
}, { deep: true })

function lineCount(text: string): number {
  return text.split('\n').length
}

function toggleCollapse(event: TaskEvent) {
  event.collapsed = !event.collapsed
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

function toolArgsSummary(args: Record<string, unknown>): string {
  const first = Object.values(args).find((v) => typeof v === 'string') as string | undefined
  if (!first) return ''
  return first.length > 80 ? first.slice(0, 80) + '...' : first
}

function formatJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
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
        class="flex-1 overflow-y-auto bg-gray-900 p-4 space-y-2"
        data-testid="log-container"
        @scroll="onScroll"
      >
        <p v-if="events.length === 0 && !finished" class="text-sm text-gray-500 italic">
          Waiting for logs...
        </p>

        <template v-for="(event, idx) in events" :key="idx">
          <!-- agent_start -->
          <div
            v-if="event.type === 'agent_start'"
            class="text-xs text-gray-500 py-1"
            data-testid="event-agent-start"
          >
            Agent started
          </div>

          <!-- agent_end -->
          <div
            v-else-if="event.type === 'agent_end'"
            class="text-xs text-gray-500 py-1"
            data-testid="event-agent-end"
          >
            Agent completed
          </div>

          <!-- thinking -->
          <div
            v-else-if="event.type === 'thinking'"
            class="rounded bg-gray-800/50 px-3 py-2"
            data-testid="event-thinking"
          >
            <div
              class="text-xs italic text-gray-400 whitespace-pre-wrap"
              :class="{ 'line-clamp-3': event.collapsed }"
            >{{ event.data.text }}</div>
            <button
              v-if="lineCount(event.data.text as string) > 3"
              class="mt-1 text-xs text-blue-400 hover:text-blue-300"
              data-testid="toggle-collapse"
              @click="toggleCollapse(event)"
            >
              {{ event.collapsed ? 'Show more' : 'Show less' }}
            </button>
          </div>

          <!-- reasoning -->
          <div
            v-else-if="event.type === 'reasoning'"
            class="rounded border-l-2 border-purple-500 bg-gray-800/50 px-3 py-2"
            data-testid="event-reasoning"
          >
            <div
              class="text-xs text-purple-300 whitespace-pre-wrap"
              :class="{ 'line-clamp-3': event.collapsed }"
            >{{ event.data.text }}</div>
            <button
              v-if="lineCount(event.data.text as string) > 3"
              class="mt-1 text-xs text-blue-400 hover:text-blue-300"
              data-testid="toggle-collapse"
              @click="toggleCollapse(event)"
            >
              {{ event.collapsed ? 'Show more' : 'Show less' }}
            </button>
          </div>

          <!-- tool_call -->
          <div
            v-else-if="event.type === 'tool_call'"
            class="rounded border border-gray-700 bg-gray-800"
            data-testid="event-tool-call"
          >
            <button
              class="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-gray-300 hover:bg-gray-700/50"
              data-testid="tool-call-header"
              @click="toggleCollapse(event)"
            >
              <span class="font-mono">{{ event.data.tool }}<span v-if="toolArgsSummary(event.data.args as Record<string, unknown>)" class="ml-2 font-normal text-gray-500 truncate">{{ toolArgsSummary(event.data.args as Record<string, unknown>) }}</span></span>
              <svg
                class="h-3 w-3 text-gray-500 transition-transform"
                :class="{ 'rotate-180': !event.collapsed }"
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            <div v-if="!event.collapsed" class="border-t border-gray-700 px-3 py-2">
              <pre class="text-xs text-gray-400 font-mono whitespace-pre-wrap" data-testid="tool-call-args">{{ formatJson(event.data.args) }}</pre>
            </div>
            <!-- tool_result appended to this card -->
            <div
              v-if="event.result"
              class="border-t border-gray-700 px-3 py-2"
              data-testid="tool-result-section"
            >
              <div class="text-xs text-gray-500 mb-1">Result ({{ event.result.length }} chars)</div>
              <pre
                class="text-xs text-gray-400 font-mono whitespace-pre-wrap"
                :class="{ 'line-clamp-3': event.result.collapsed }"
                data-testid="tool-result-output"
              >{{ event.result.output }}</pre>
              <button
                v-if="lineCount(event.result.output) > 3"
                class="mt-1 text-xs text-blue-400 hover:text-blue-300"
                data-testid="toggle-result-collapse"
                @click="event.result.collapsed = !event.result.collapsed"
              >
                {{ event.result.collapsed ? 'Show more' : 'Show less' }}
              </button>
            </div>
          </div>

          <!-- error -->
          <div
            v-else-if="event.type === 'error'"
            class="rounded bg-red-900/50 border border-red-700 px-3 py-2 text-xs text-red-300"
            data-testid="event-error"
          >
            {{ event.data.message }}
          </div>

          <!-- raw -->
          <div
            v-else-if="event.type === 'raw'"
            class="text-xs font-mono text-gray-400 whitespace-pre-wrap"
            data-testid="event-raw"
          >{{ event.data.line }}</div>
        </template>

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
