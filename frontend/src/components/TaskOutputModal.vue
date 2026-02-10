<script setup lang="ts">
import { ref, onMounted } from 'vue'

defineProps<{
  title: string
  output: string | null
}>()

const emit = defineEmits<{
  close: []
}>()

const dialogRef = ref<HTMLDialogElement | null>(null)

onMounted(() => {
  dialogRef.value?.showModal()
})

function onClose() {
  dialogRef.value?.close()
  emit('close')
}
</script>

<template>
  <dialog
    ref="dialogRef"
    class="rounded-lg p-0 shadow-xl backdrop:bg-black/50"
    @cancel.prevent="onClose"
    @click.self="onClose"
  >
    <div class="w-[36rem] max-h-[80vh] flex flex-col p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold text-gray-800 truncate">{{ title }}</h3>
        <button
          type="button"
          class="text-gray-400 hover:text-gray-600"
          @click="onClose"
          aria-label="Close"
        >
          <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div class="flex-1 overflow-auto rounded-md border border-gray-200 bg-gray-50 p-4">
        <pre v-if="output" class="whitespace-pre-wrap break-words text-sm font-mono text-gray-700">{{ output }}</pre>
        <p v-else class="text-sm text-gray-500 italic">No output available</p>
      </div>
      <div class="mt-4 flex justify-end">
        <button
          type="button"
          class="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          @click="onClose"
        >
          Close
        </button>
      </div>
    </div>
  </dialog>
</template>
