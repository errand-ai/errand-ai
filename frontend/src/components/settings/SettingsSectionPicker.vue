<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

interface Section {
  id: string
  label: string
  to: string
}

const props = defineProps<{
  sections: Section[]
  activeRoute: string
}>()

const emit = defineEmits<{
  (e: 'change', to: string): void
}>()

const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)
const listEl = ref<HTMLElement | null>(null)
const triggerEl = ref<HTMLButtonElement | null>(null)
const highlightedIndex = ref(0)

const activeSection = computed<Section | undefined>(() =>
  props.sections.find(s => s.to === props.activeRoute),
)

const activeLabel = computed(() => activeSection.value?.label ?? 'Select section')

function activeIndex(): number {
  const idx = props.sections.findIndex(s => s.to === props.activeRoute)
  return idx >= 0 ? idx : 0
}

function focusOption(index: number) {
  const node = listEl.value?.querySelectorAll<HTMLElement>('[role="option"]')[index]
  node?.focus()
}

async function openPanel(initialIndex?: number) {
  open.value = true
  highlightedIndex.value = initialIndex ?? activeIndex()
  await nextTick()
  focusOption(highlightedIndex.value)
}

function closePanel({ returnFocus = false } = {}) {
  open.value = false
  if (returnFocus) {
    nextTick(() => triggerEl.value?.focus())
  }
}

function togglePanel() {
  if (open.value) {
    closePanel({ returnFocus: true })
  } else {
    openPanel()
  }
}

function selectSection(section: Section) {
  emit('change', section.to)
  closePanel({ returnFocus: true })
}

function onKeydownButton(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    togglePanel()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    openPanel(0)
  }
}

function onKeydownOption(e: KeyboardEvent, index: number) {
  if (e.key === 'Escape') {
    e.preventDefault()
    closePanel({ returnFocus: true })
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlightedIndex.value = Math.min(props.sections.length - 1, index + 1)
    focusOption(highlightedIndex.value)
    return
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlightedIndex.value = Math.max(0, index - 1)
    focusOption(highlightedIndex.value)
    return
  }
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    const section = props.sections[index]
    if (section) selectSection(section)
    return
  }
  if (e.key === 'Home') {
    e.preventDefault()
    highlightedIndex.value = 0
    focusOption(0)
    return
  }
  if (e.key === 'End') {
    e.preventDefault()
    highlightedIndex.value = props.sections.length - 1
    focusOption(highlightedIndex.value)
  }
}

function onDocumentClick(e: MouseEvent) {
  if (!open.value) return
  const target = e.target as Node | null
  if (rootEl.value && target && !rootEl.value.contains(target)) {
    // Pointer-driven close: do not steal focus back to the trigger — the
    // user may have intentionally clicked another focusable control.
    closePanel()
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    document.addEventListener('click', onDocumentClick)
  } else {
    document.removeEventListener('click', onDocumentClick)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <div ref="rootEl" class="relative" data-testid="settings-section-picker">
    <button
      ref="triggerEl"
      type="button"
      class="flex w-full items-center justify-between rounded-md border border-gray-300 bg-white px-3 py-2 text-left text-sm font-medium text-gray-900 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      :aria-expanded="open"
      aria-haspopup="listbox"
      data-testid="settings-section-picker-button"
      @click="togglePanel"
      @keydown="onKeydownButton"
    >
      <span class="truncate">{{ activeLabel }}</span>
      <svg
        class="ml-2 h-4 w-4 flex-shrink-0 text-gray-500 transition-transform"
        :class="open ? 'rotate-180' : ''"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fill-rule="evenodd"
          d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z"
          clip-rule="evenodd"
        />
      </svg>
    </button>

    <ul
      v-if="open"
      ref="listEl"
      role="listbox"
      tabindex="-1"
      class="absolute left-0 right-0 z-20 mt-1 max-h-72 overflow-auto rounded-md border border-gray-200 bg-white py-1 shadow-lg focus:outline-none"
      data-testid="settings-section-picker-panel"
    >
      <li
        v-for="(section, index) in sections"
        :key="section.id"
        role="option"
        tabindex="-1"
        :aria-selected="section.to === activeRoute"
        class="cursor-pointer px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 focus:bg-gray-100 focus:outline-none"
        :class="section.to === activeRoute ? 'bg-gray-100 font-medium text-gray-900' : ''"
        :data-testid="`settings-section-picker-option-${section.id}`"
        @click="selectSection(section)"
        @keydown="onKeydownOption($event, index)"
        @mouseenter="() => { highlightedIndex = index; focusOption(index) }"
      >
        {{ section.label }}
      </li>
    </ul>
  </div>
</template>
