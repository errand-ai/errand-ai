<script lang="ts">
export interface TaskEvent {
  type: string
  data: Record<string, unknown>
  collapsed?: boolean
  result?: { output: string; length: number; collapsed: boolean }
}
</script>

<script setup lang="ts">
defineProps<{
  events: TaskEvent[]
}>()

function lineCount(text: string): number {
  return text.split('\n').length
}

function toggleCollapse(event: TaskEvent) {
  event.collapsed = !event.collapsed
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
</script>

<template>
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
</template>
