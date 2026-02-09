import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import KanbanBoard from '../components/KanbanBoard.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: KanbanBoard,
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../pages/SettingsPage.vue'),
      meta: { requiresAdmin: true },
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAdmin) {
    const auth = useAuthStore()
    if (!auth.isAdmin) {
      return { name: 'home' }
    }
  }
})

export default router
