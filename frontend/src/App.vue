<script setup lang="ts">
import KanbanBoard from './components/KanbanBoard.vue'
</script>

<template>
  <div class="min-h-screen bg-gray-100">
    <header class="bg-white shadow">
      <div class="mx-auto max-w-7xl px-4 py-4">
        <h1 class="text-2xl font-bold text-gray-900">Content Manager</h1>
      </div>
    </header>
    <main class="mx-auto max-w-7xl px-4 py-6">
      <KanbanBoard />
    </main>
  </div>
</template>
