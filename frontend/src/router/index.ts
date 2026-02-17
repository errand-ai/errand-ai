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
      path: '/archived',
      name: 'archived',
      component: () => import('../pages/ArchivedTasksPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/settings',
      component: () => import('../pages/SettingsPage.vue'),
      meta: { requiresAdmin: true },
      children: [
        {
          path: '',
          redirect: { name: 'settings-agent' },
        },
        {
          path: 'agent',
          name: 'settings-agent',
          component: () => import('../pages/settings/AgentConfigurationPage.vue'),
        },
        {
          path: 'tasks',
          name: 'settings-tasks',
          component: () => import('../pages/settings/TaskManagementPage.vue'),
        },
        {
          path: 'security',
          name: 'settings-security',
          component: () => import('../pages/settings/SecurityPage.vue'),
        },
        {
          path: 'integrations',
          name: 'settings-integrations',
          component: () => import('../pages/settings/IntegrationsPage.vue'),
        },
        {
          path: ':pathMatch(.*)*',
          redirect: { name: 'settings-agent' },
        },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'home' }
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'home' }
  }
})

export default router
